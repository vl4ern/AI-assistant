type HealthStatus = {
  status: string;
  service: string;
  version: string;
};

async function getBackendHealth(): Promise<HealthStatus | null> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${baseUrl}/health`, {
      cache: "no-store",
    });

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as HealthStatus;
  } catch {
    return null;
  }
}

export default async function Home() {
  const health = await getBackendHealth();

  return (
    <main className="page">
      <section className="hero">
        <p className="hero__eyebrow">Course Project v1</p>
        <h1>Интеллектуальный ассистент для учебных дедлайнов</h1>
        <p className="hero__description">
          Базовая архитектура уже собрана: Web, API, планировщик, интеграции и
          контракты между модулями.
        </p>
      </section>

      <section className="cards">
        <article className="card">
          <h2>Frontend</h2>
          <p>
            <code>apps/web</code>
          </p>
          <p>Сегодня, календарь, проекты, аналитика и настройки.</p>
        </article>

        <article className="card">
          <h2>Intelligence</h2>
          <p>
            <code>apps/api/app/modules/intelligence</code>
          </p>
          <p>Greedy planner, scoring, prime-task, перепланирование.</p>
        </article>

        <article className="card">
          <h2>Knowledge Base</h2>
          <p>
            <code>apps/api/app/modules/knowledge</code>
          </p>
          <p>Сущности задач/событий, репозиторий и флаг dirty schedule.</p>
        </article>

        <article className="card">
          <h2>Integrations</h2>
          <p>
            <code>apps/api/app/modules/integrations</code>
          </p>
          <p>Провайдеры Google/GitHub/LMS и единый sync-интерфейс.</p>
        </article>
      </section>

      <section className="status">
        <h2>Статус API</h2>
        {health ? (
          <p>
            {health.service} {health.version}: <strong>{health.status}</strong>
          </p>
        ) : (
          <p>API недоступно. Запусти make api-dev или docker compose up.</p>
        )}
      </section>
    </main>
  );
}
