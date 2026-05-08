from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean

from app.modules.knowledge.models import Event, Task
from app.modules.intelligence.utils.time_utils import build_working_windows

from sklearn.linear_model import SGDRegressor
from sklearn.preprocessing import StandardScaler


@dataclass
class TrainingSample:
    """
    Один обучающий пример для дообучения модели.

    Хранит исходные данные, а не готовые признаки, чтобы при каждом
    пересчёте признаков учитывать актуальные веса рабочих областей.
    """
    task: Task
    events: list[Event]
    now: datetime
    target: float
    source: str
    task_id: str


class MLScoringService:
    """
    Сервис скоринга задач на основе линейной регрессии (SGDRegressor).

    Модель сразу готова к работе благодаря стартовой калибровке на синтетических данных,
    сгенерированных по эвристической формуле. В процессе эксплуатации модель дообучается
    на реальных действиях пользователя (завершение задач).

    Признаки модели (5):
    - свободные минуты до дедлайна (с учётом событий и времени бодрствования);
    - приоритет задачи (1-4);
    - оценка времени выполнения (минуты);
    - длина описания (символы) – чем длиннее описание, тем задача может быть сложнее/важнее;
    - вес рабочей области (workspace) – динамический показатель, обучаемый на основе
      обратной связи пользователя (0 для новых областей, средний целевой скор – для известных).

    Основные методы:
    - build_score_map() – формирует словарь {task_id: score} с учётом зависимостей.
    - record_completed_feedback() – накапливает обучающие примеры для онлайн-обучения
      с адаптивным целевым скором (ориентация на топ-задачу и бонус за просрочку).
    - record_reorder_feedback() – альтернативный канал обратной связи (оставлен для совместимости).
    """

    def __init__(
        self,
        wake_start_hour: int,
        wake_end_hour: int,
        horizon_days: int,
        retrain_batch_size: int = 20,
        overdue_bonus: float = 7.0,
    ) -> None:
        """
        Инициализирует сервис.

        Параметры:
            wake_start_hour: час начала бодрствования (для расчёта признака свободного времени).
            wake_end_hour: час окончания бодрствования (24 – если до полуночи).
            horizon_days: горизонт планирования в днях (для задач без дедлайна).
            retrain_batch_size: размер пакета, при котором выполняется частичное обучение.
            overdue_bonus: базовый бонус к скору просроченной задачи (может увеличиваться
                           фактической длительностью опоздания).
        """
        self.wake_start_hour = wake_start_hour
        self.wake_end_hour = wake_end_hour
        self.horizon_days = horizon_days
        self.retrain_batch_size = retrain_batch_size
        self.overdue_bonus = overdue_bonus
        self._scaler = StandardScaler()

        self._model = SGDRegressor(
            loss="squared_error",
            penalty="l2",
            random_state=42,
            max_iter=2000,
            tol=1e-3,
            learning_rate="optimal"
        )

        # Накопление статистики по весам рабочих областей
        self._ws_sum: dict[str, float] = {}
        self._ws_count: dict[str, int] = {}

        self._pending_samples: list[TrainingSample] = []
        self.last_scores: dict[str, float] = {}
        self._bootstrap_model()

    @property
    def pending_samples_count(self) -> int:
        """Возвращает количество накопленных (но ещё не использованных) обучающих примеров."""
        return len(self._pending_samples)

    def build_score_map(
        self,
        tasks: list[Task],
        events: list[Event],
        now: datetime,
    ) -> dict[str, float]:
        """
        Вычисляет скоры для всех задач.

        Для каждой задачи вычисляется индивидуальный скор через модель, затем применяются
        правила зависимостей (блокирующие задачи повышают свой приоритет).

        Возвращает словарь {task_id: score}. Результат также сохраняется в last_scores.
        """
        current = self._to_utc(now)
        score_map = {
            task.id: self.score_single_task(task=task, events=events, now=current)
            for task in tasks
        }
        self._apply_dependency_rules(tasks=tasks, score_map=score_map)
        self.last_scores = score_map.copy()
        return score_map

    def score_single_task(self, task: Task, events: list[Event], now: datetime) -> float:
        """
        Возвращает скор одной задачи, предсказанный ML-моделью.

        Признаки: [свободные минуты до дедлайна, приоритет, оценка времени,
                   длина описания, вес рабочей области].
        """
        features = self._task_features(task=task, events=events, now=now)
        return float(self._model.predict([features])[0])

    def record_reorder_feedback(
        self,
        task: Task,
        events: list[Event],
        now: datetime,
        target_score: float,
    ) -> bool:
        """
        Регистрирует обучающий пример на основе ручного переупорядочивания задачи.

        Возвращает True, если был выполнен partial_fit (накоплен полный пакет).
        """
        return self._record_sample(
            task=task,
            events=events,
            now=now,
            target_score=target_score,
            source="reorder",
        )

    def record_completed_feedback(
        self,
        task: Task,
        events: list[Event],
        now: datetime,
        base_score: float,
        max_active_score: float | None = None,
    ) -> bool:
        """
        Регистрирует обучающий пример по факту завершения задачи.

        Целевой скор адаптируется с учётом текущего лидера среди активных задач
        и степени просрочки:

        - Если задача просрочена, то target = max(max_active_score, base_score) + overdue_bonus,
          где overdue_bonus может быть увеличен пропорционально количеству дней просрочки.
        - Если не просрочена и есть более приоритетная задача (max_active_score > base_score),
          target = max_active_score + 0.5 * (max_active_score - base_score)
          (завершённая задача должна была быть не хуже лидера с небольшим бонусом).
        - Иначе target = base_score (задача уже имела высший скор).

        Возвращает True, если был выполнен partial_fit.
        """
        
        now_utc = self._to_utc(now)
        target = base_score

        deadline = task.deadline
        overdue = deadline and self._to_utc(deadline) < now_utc
        days_late = 0.0
        if overdue:
            delta = now_utc - self._to_utc(deadline)
            days_late = delta.total_seconds() / 86400.0
            # Увеличиваем бонус за просрочку в зависимости от длительности опоздания
            dynamic_bonus = self.overdue_bonus * (1.0 + days_late)
            target += dynamic_bonus
        elif max_active_score:
            leader = max(max_active_score, base_score)
            target = leader + 0.5 * (leader - base_score)

        return self._record_sample(
            task=task,
            events=events,
            now=now,
            target_score=target,
            source="completed",
        )

    def _record_sample(
        self,
        task: Task,
        events: list[Event],
        now: datetime,
        target_score: float,
        source: str,
    ) -> bool:
        """
        Добавляет обучающий пример в очередь и при необходимости дообучает модель.

        Обновляет статистику рабочей области на основе целевого скора, затем сохраняет
        TrainingSample с исходными данными. При накоплении retrain_batch_size примеров
        пересчитывает признаки с актуальными весами и выполняет partial_fit.

        Возвращает True, если модель была дообучена.
        """
        # Обновляем вес рабочей области
        ws = task.workspace_id
        self._ws_sum[ws] = self._ws_sum.get(ws, 0.0) + target_score
        self._ws_count[ws] = self._ws_count.get(ws, 0) + 1

        self._pending_samples.append(
            TrainingSample(
                task=task,
                events=events,
                now=now,
                target=float(target_score),
                source=source,
                task_id=task.id,
            )
        )

        if len(self._pending_samples) < self.retrain_batch_size:
            return False

        features_batch = [
            self._task_features(s.task, s.events, s.now)
            for s in self._pending_samples
        ]
        targets_batch = [s.target for s in self._pending_samples]
        print ('\nЯ ОБУЧИЛСЯ\n')
        self._model.partial_fit(features_batch, targets_batch)
        self._pending_samples.clear()
        return True
    

    def _task_features(self, task: Task, events: list[Event], now: datetime) -> list[float]:
        """
        Формирует вектор признаков для задачи из 5 элементов:
        [free_minutes_to_deadline, user_priority, estimated_minutes,
         description_length, workspace_weight].

        Длина описания и вес рабочей области – дополнительные сигналы,
        повышающие качество планирования.
        """
        free_minutes = self._time_to_deadline_free_minutes(task=task, events=events, now=now)
        user_priority = float(task.priority)
        estimate_minutes = float(task.estimated_minutes)
        desc_len = float(len(task.description or ""))
        ws_weight = self._get_workspace_weight(task.workspace_id)

        raw = [[free_minutes, user_priority, estimate_minutes, desc_len, ws_weight]]
        return list(self._scaler.transform(raw)[0])

    def _get_workspace_weight(self, workspace_id: str) -> float:
        """
        Возвращает текущий вес рабочей области как среднее целевых скоров
        по всем записанным примерам обратной связи для этой области.
        Для неизвестной области возвращает 0.
        """
        cnt = self._ws_count.get(workspace_id, 0)
        if cnt == 0:
            return 0.0
        return self._ws_sum[workspace_id] / cnt

    def _time_to_deadline_free_minutes(self, task: Task, events: list[Event], now: datetime) -> float:
        """
        Вычисляет количество свободных минут (с учётом событий) в окнах бодрствования
        от текущего момента до дедлайна задачи. Если дедлайн отсутствует, используется horizon_days.
        """
        current = self._to_utc(now)
        deadline = (
            self._to_utc(task.deadline)
            if task.deadline is not None
            else current + timedelta(days=self.horizon_days)
        )

        if deadline <= current:
            return 0.0

        awake_windows = build_working_windows(current, deadline, self.wake_start_hour, self.wake_end_hour)
        awake_minutes = sum((end - start).total_seconds() / 60 for start, end in awake_windows)
        busy_minutes = self._events_overlap_minutes(windows=awake_windows, events=events)

        return max(0.0, awake_minutes - busy_minutes)

    def _events_overlap_minutes(
        self,
        windows: list[tuple[datetime, datetime]],
        events: list[Event],
    ) -> float:
        """
        Суммирует минуты пересечения переданных окон с заданными событиями.

        Используется для вычитания занятого времени из свободного.
        """
        busy = 0.0
        normalized_events = [
            (self._to_utc(event.start_at), self._to_utc(event.end_at))
            for event in events
            if event.end_at > event.start_at
        ]

        for window_start, window_end in windows:
            for event_start, event_end in normalized_events:
                overlap_start = max(window_start, event_start)
                overlap_end = min(window_end, event_end)
                if overlap_end > overlap_start:
                    busy += (overlap_end - overlap_start).total_seconds() / 60

        return busy

    def _apply_dependency_rules(self, tasks: list[Task], score_map: dict[str, float]) -> None:
        """
        Корректирует скоры с учётом зависимостей между задачами.

        Логика:
        - Скор задачи с зависимостями становится средним между её собственным скором и скорами блокирующих задач.
        - Блокирующие задачи получают скор не ниже среднего + 1, чтобы они выполнялись раньше.
        """
        task_by_id = {task.id: task for task in tasks}
        base_scores = score_map.copy()

        for task in tasks:
            blockers = [
                task_by_id[dep_id]
                for dep_id in task.depends_on
                if dep_id in base_scores
            ]
            if not blockers or task.id not in base_scores:
                continue

            dependent_score = mean(
                [base_scores[task.id], *[base_scores[item.id] for item in blockers]]
            )
            score_map[task.id] = dependent_score

            blocker_target = dependent_score + 1.0
            for blocker in blockers:
                score_map[blocker.id] = max(score_map[blocker.id], blocker_target)

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        """
        Приводит datetime к UTC.

        Если временная зона отсутствует, считает, что значение уже в UTC.
        """
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _bootstrap_model(self) -> None:
        """
        Начальное обучение модели на синтетическом датасете.

        Генерирует примеры с пятью признаками:
        [free_minutes, priority, estimate_minutes, description_length, workspace_weight].
        Длина описания варьируется синтетически (0, 50, 200, 500 символов),
        вес рабочей области – 0 (на старте реальных данных нет).
        """
        bootstrap_features: list[list[float]] = []
        bootstrap_targets: list[float] = []

        free_minutes_values = [30, 60, 180, 240, 720, 1440, 2880, 7200, 10000, 14400, 20000, 28800, 35000, 43200]
        priorities = [1, 2, 3, 4]
        estimates = [30, 60, 90, 120, 150, 180, 210, 240, 270, 300]
        desc_lengths = [0, 50, 200, 500, 2000]
        
        # Добавим несколько значений workspace_weight, чтобы scaler их знал
        ws_weights = [0.0, 50.0, 200.0, 800.0, 2000.0]


        for free_minutes in free_minutes_values:
            for priority in priorities:
                for estimate in estimates:
                    for desc_len in desc_lengths:
                        for ws_w in ws_weights:
                            bootstrap_features.append([
                                float(free_minutes),
                                float(priority),
                                float(estimate),
                                float(desc_len),
                                ws_w
                            ])
                            bootstrap_targets.append(
                                self._initial_target(
                                    free_minutes=float(free_minutes),
                                    priority=float(priority),
                                    estimated_minutes=float(estimate),
                                    description_length=float(desc_len),
                                )
                            )

        self._scaler.fit(bootstrap_features)
        X_scaled = self._scaler.transform(bootstrap_features)
        self._model.fit(X_scaled, bootstrap_targets)

    @staticmethod
    def _initial_target(
        free_minutes: float,
        priority: float,
        estimated_minutes: float,
        description_length: float = 0.0,
    ) -> float:
        """
        Начальная формула "здравого смысла":
        - чем меньше свободного времени до дедлайна, тем выше score;
        - чем "важнее" задача для пользователя (priority=1), тем выше score;
        - более длинные задачи немного повышаем, чтобы не откладывались бесконечно;
        - бонус за объём описания (0.01 * длина_в_символах) – эвристика «подробнее → сложнее/важнее».
        """
        raw = (1025.0 - 0.006 * free_minutes
            - 25.0 * priority
            + 0.05 * estimated_minutes
            + 0.01 * description_length)
        return raw
