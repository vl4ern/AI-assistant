function Topbar(){
    return(
        <header className="topbar">
            <div className="search-box">Search tasks, project, deadlines...</div>

            <div className="topbar-right">
                <button className="secondary-button">Open Calendar</button>
                <button className="primary-button">New Task</button>
                <div className="profile-badge">X</div>
            </div>
        </header>
    );
}

export default Topbar;