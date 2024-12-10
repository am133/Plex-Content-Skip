from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, JSON, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Optional, List
import sqlalchemy

# Database setup
DATABASE_URL = "sqlite:///./media.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Database Models
class Movie(Base):
    __tablename__ = "movies"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, unique=True, index=True)
    timestamps = Column(JSON)

class TVShow(Base):
    __tablename__ = "tv_shows"
    id = Column(Integer, primary_key=True, index=True)
    show_name = Column(String, index=True)
    season = Column(String)
    episode_number = Column(String)
    title = Column(String)
    timestamps = Column(JSON)

    __table_args__ = (
        UniqueConstraint('show_name', 'season', 'episode_number', name='unique_episode'),
    )

# Pydantic Models for Request Validation
class TimestampData(BaseModel):
    viewOffset: float  # Just storing the playback time in seconds

class AddMovieRequest(BaseModel):
    title: str
    timestamps: List[TimestampData]

class AddTVShowRequest(BaseModel):
    show_name: str
    season: str
    episode_number: str
    title: str
    timestamps: List[TimestampData]

class GetMediaRequest(BaseModel):
    title: str
    show_name: Optional[str] = None
    season: Optional[str] = None
    episode_number: Optional[str] = None

# FastAPI app
app = FastAPI()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Movie Endpoints
@app.post("/movies/add-timestamps/")
def add_movie_timestamps(request: AddMovieRequest, db: Session = Depends(get_db)):
    existing_movie = db.query(Movie).filter(Movie.title == request.title).first()

    if existing_movie:
        current_timestamps = existing_movie.timestamps.copy() if existing_movie.timestamps else []

        # Convert timestamps to dict for storage
        timestamps_as_dict = [ts.dict() for ts in request.timestamps]

        # Create a set of existing timestamps for comparison
        existing_timestamp_set = {
            ts['viewOffset']
            for ts in current_timestamps
        }

        added_new = False
        for new_ts in timestamps_as_dict:
            if new_ts['viewOffset'] not in existing_timestamp_set:
                current_timestamps.append(new_ts)
                existing_timestamp_set.add(new_ts['viewOffset'])
                added_new = True

        if added_new:
            existing_movie.timestamps = None
            db.flush()
            existing_movie.timestamps = current_timestamps
            db.flush()
            db.commit()
            db.refresh(existing_movie)

        return {
            "message": f"Timestamps updated for movie '{existing_movie.title}'",
            "updated_timestamps": existing_movie.timestamps
        }

    new_movie = Movie(
        title=request.title,
        timestamps=[ts.dict() for ts in request.timestamps]
    )
    db.add(new_movie)
    db.commit()
    db.refresh(new_movie)
    return {"message": "Movie and timestamps added successfully!"}

@app.post("/movies/get-timestamps/")
def get_movie_timestamps(request: GetMediaRequest, db: Session = Depends(get_db)):
    movie = db.query(Movie).filter(Movie.title == request.title).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return {
        "title": movie.title,
        "timestamps": movie.timestamps
    }

# TV Show Endpoints
@app.post("/tv-shows/add-timestamps/")
def add_tvshow_timestamps(request: AddTVShowRequest, db: Session = Depends(get_db)):
    existing_episode = db.query(TVShow).filter(
        TVShow.show_name == request.show_name,
        TVShow.season == request.season,
        TVShow.episode_number == request.episode_number
    ).first()

    if existing_episode:
        current_timestamps = existing_episode.timestamps.copy() if existing_episode.timestamps else []

        # Convert timestamps to dict for storage
        timestamps_as_dict = [ts.dict() for ts in request.timestamps]

        existing_timestamp_set = {
            ts['viewOffset']
            for ts in current_timestamps
        }

        added_new = False
        for new_ts in timestamps_as_dict:
            if new_ts['viewOffset'] not in existing_timestamp_set:
                current_timestamps.append(new_ts)
                existing_timestamp_set.add(new_ts['viewOffset'])
                added_new = True

        if added_new:
            existing_episode.timestamps = None
            db.flush()
            existing_episode.timestamps = current_timestamps
            db.flush()
            db.commit()
            db.refresh(existing_episode)

        return {
            "message": f"Timestamps updated for TV show '{existing_episode.show_name}' S{existing_episode.season}E{existing_episode.episode_number}",
            "updated_timestamps": existing_episode.timestamps
        }

    new_episode = TVShow(
        show_name=request.show_name,
        season=request.season,
        episode_number=request.episode_number,
        title=request.title,
        timestamps=[ts.dict() for ts in request.timestamps]
    )
    db.add(new_episode)
    db.commit()
    db.refresh(new_episode)
    return {"message": "TV show episode and timestamps added successfully!"}

@app.post("/tv-shows/get-timestamps/")
def get_tvshow_timestamps(request: GetMediaRequest, db: Session = Depends(get_db)):
    if not all([request.show_name, request.season, request.episode_number]):
        raise HTTPException(
            status_code=400,
            detail="show_name, season, and episode_number are required for TV shows"
        )

    episode = db.query(TVShow).filter(
        TVShow.show_name == request.show_name,
        TVShow.season == request.season,
        TVShow.episode_number == request.episode_number
    ).first()

    if not episode:
        raise HTTPException(status_code=404, detail="TV show episode not found")

    return {
        "show_name": episode.show_name,
        "season": episode.season,
        "episode_number": episode.episode_number,
        "title": episode.title,
        "timestamps": episode.timestamps
    }

# Create tables
Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend:app", host="127.0.0.1", port=8000, reload=True)