import { useState } from 'react';

const navItems = [
  'Dashboard',
  'Tasks',
  'Projects',
  'Calendar',
  'Analytics',
  'Settings',
  'Notifications',
];

function Sidebar() {
  const [activeItem, setActiveItem] = useState('Dashboard');

  return (
    <aside className="sidebar">
      <h2 className="logo">AI Assistant</h2>

      <nav className="sidebar-nav">
        <ul>
          {navItems.map((item) => (
            <li
              key={item}
              className={`nav-item ${activeItem === item ? 'active' : ''}`}
            >
              <a
                href="#"
                onClick={(event) => {
                  event.preventDefault();
                  setActiveItem(item);
                }}
              >
                {item}
              </a>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}

export default Sidebar;