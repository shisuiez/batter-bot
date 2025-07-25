ALTER TABLE users ADD COLUMN IF NOT EXISTS total_distance FLOAT DEFAULT 0.0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS total_elevation INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS hikes_count INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS rank VARCHAR(32) DEFAULT 'Новичок';

CREATE TABLE IF NOT EXISTS routes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    distance FLOAT NOT NULL,
    elevation INTEGER NOT NULL,
    description TEXT NOT NULL,
    difficulty VARCHAR(32) NOT NULL,
    latitude FLOAT,
    longitude FLOAT
);

CREATE TABLE IF NOT EXISTS hikes (
    id SERIAL PRIMARY KEY,
    route_id INTEGER REFERENCES routes(id),
    date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS hike_participants (
    id SERIAL PRIMARY KEY,
    hike_id INTEGER REFERENCES hikes(id),
    user_id INTEGER REFERENCES users(id),
    completed INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS achievements (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    description TEXT NOT NULL,
    icon VARCHAR(8) NOT NULL
);

CREATE TABLE IF NOT EXISTS user_achievements (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    achievement_id INTEGER REFERENCES achievements(id)
); 