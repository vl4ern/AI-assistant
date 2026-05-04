type Task = {
  id: number;
  title: string;
  priority: string;
};

type TaskListProps = {
  tasks: Task[];
};

function TaskList({ tasks }: TaskListProps) {
  return (
    <section className="content-section">
      <h2>Today's Tasks</h2>

      <ul className="task-list">
        {tasks.map((task) => (
          <li key={task.id} className="task-item">
            <div>
              <p className="task-title">{task.title}</p>
              <p className="task-priority">Priority: {task.priority}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default TaskList;