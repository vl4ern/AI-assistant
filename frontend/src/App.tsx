import { useState } from 'react';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import StatCard from './components/StatCard';
import TaskList from './components/TaskList';

function App() {
  const [tasksToday, setTasksToday] = useState(5);

  const tasks = [
    { id: 1, title: 'Finish homework', priority: 'High' },
    { id: 2, title: 'Create database report', priority: 'Medium' },
    { id: 3, title: 'Read AI lecture notes', priority: 'Low' },
  ];

  return (
    <div className="app-layout">
      <Sidebar />

      <div className="page-content">
        <Topbar />

        <section className="page-header">
          <h1>Dashboard</h1>
          <p>Plan smarter, study better.</p>
        </section>

        <section className="overview-section">
          <div className="overview-header">
            <div>
              <h2 className="overview-title">Overview</h2>
              <p className="overview-subtitle">
                Quick actions and daily statistics
              </p>
            </div>

            <div className="action-group">
              <button
                className="secondary-button"
                onClick={() =>
                  setTasksToday((prevTasks) =>
                    prevTasks > 0 ? prevTasks - 1 : 0
                  )
                }
              >
                Remove task
              </button>

              <button
                className="primary-button"
                onClick={() => setTasksToday((prevTasks) => prevTasks + 1)}
              >
                Add task
              </button>
            </div>
          </div>

          <div className="overview-grid">
            <StatCard label="Tasks Today" value={String(tasksToday)} />
            <StatCard label="Active Projects" value="3" />
            <StatCard label="Deadlines This Week" value="5" />
            <StatCard label="Study Hours" value="6h" />
            <StatCard label="Completed Tasks" value="9" />
          </div>
        </section>

        <section className="dashboard-content">
          <TaskList tasks={tasks} />
        </section>
      </div>
    </div>
  );
}

export default App;