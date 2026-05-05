type KnowledgeBasePanelProps = {
  totalTasks: number;
  activeTasks: number;
  completedTasks: number;
  highPriorityTasks: number;
};

const panelStyle = {
  display: 'grid',
  gap: '20px',
  padding: '24px',
  marginBottom: '24px',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '24px',
  background:
    'linear-gradient(135deg, rgba(37,99,235,0.18), rgba(15,23,42,0.92)), rgba(15,23,42,0.9)',
  boxShadow: 'var(--shadow)',
} as const;

const descriptionStyle = {
  margin: 0,
  maxWidth: '820px',
  color: 'var(--muted)',
  lineHeight: 1.6,
} as const;

const gridStyle = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
  gap: '14px',
} as const;

const cardStyle = {
  padding: '16px',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '18px',
  background: 'rgba(8,17,32,0.55)',
} as const;

const cardLabelStyle = {
  display: 'block',
  color: 'var(--muted)',
  fontSize: '0.85rem',
  marginBottom: '8px',
} as const;

const cardValueStyle = {
  fontSize: '1.7rem',
} as const;

const factsStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: '10px',
} as const;

const factBadgeStyle = {
  padding: '8px 12px',
  borderRadius: '999px',
  background: 'rgba(255,255,255,0.08)',
  color: '#dbeafe',
  fontSize: '0.85rem',
} as const;

export function KnowledgeBasePanel({
  totalTasks,
  activeTasks,
  completedTasks,
  highPriorityTasks,
}: KnowledgeBasePanelProps) {
  const facts = ['Task', 'Event', 'Dependency', 'Deadline', 'Priority', 'Status'];

  return (
    <section style={panelStyle}>
      <div>
        <p className="eyebrow">Knowledge Base MVP</p>
        <h2 style={{ margin: '4px 0 8px', fontSize: '1.6rem' }}>
          База знаний ассистента
        </h2>
        <p style={descriptionStyle}>
          Система хранит структурированные знания о задачах, событиях, дедлайнах,
          приоритетах и зависимостях. Данные сохраняются в PostgreSQL и проходят
          проверку правил на backend.
        </p>
      </div>

      <div style={gridStyle}>
        <div style={cardStyle}>
          <span style={cardLabelStyle}>Всего задач</span>
          <strong style={cardValueStyle}>{totalTasks}</strong>
        </div>

        <div style={cardStyle}>
          <span style={cardLabelStyle}>Активные</span>
          <strong style={cardValueStyle}>{activeTasks}</strong>
        </div>

        <div style={cardStyle}>
          <span style={cardLabelStyle}>Выполненные</span>
          <strong style={cardValueStyle}>{completedTasks}</strong>
        </div>

        <div style={cardStyle}>
          <span style={cardLabelStyle}>Высокий приоритет</span>
          <strong style={cardValueStyle}>{highPriorityTasks}</strong>
        </div>
      </div>

      <div style={factsStyle}>
        {facts.map((fact) => (
          <span key={fact} style={factBadgeStyle}>
            {fact}
          </span>
        ))}
      </div>
    </section>
  );
}
