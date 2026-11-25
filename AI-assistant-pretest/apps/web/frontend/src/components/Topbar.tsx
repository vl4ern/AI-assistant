// Импортируем картинку из папки assets
import myImage from '../assets/kurs.jpg';

function Topbar() {
  return (
    <header className="topbar">
      <div className="search-box">Search tasks, project, deadlines...</div>

      <div className="topbar-right">
        <button className="secondary-button">Open Calendar</button>
        <button className="primary-button">New Task</button>

        {/* Аватарка пользователя */}
        <div className="profile-badge">
          <img src={myImage} alt="User avatar" className="profile-image" />
        </div>
      </div>
    </header>
  );
}

export default Topbar;