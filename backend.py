from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
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
    timestamps = Column(JSON)  # Changed back to timestamps


class TVShow(Base):
    __tablename__ = "tv_shows"
    id = Column(Integer, primary_key=True, index=True)
    show_name = Column(String, index=True)
    season = Column(String)
    episode_number = Column(String)
    title = Column(String)
    timestamps = Column(JSON)  # Changed back to timestamps

    __table_args__ = (
        UniqueConstraint('show_name', 'season', 'episode_number', name='unique_episode'),
    )


# Pydantic Models for Request Validation
class TimestampRange(BaseModel):
    start_time: float = Field(..., description="Start time of the range in seconds")
    end_time: float = Field(..., description="End time of the range in seconds")
    label: Optional[str] = Field(None, description="Optional label for this timestamp range")


class AddMovieRequest(BaseModel):
    title: str
    timestamps: List[TimestampRange]  # Changed to match expected field name


class AddTVShowRequest(BaseModel):
    show_name: str
    season: str
    episode_number: str
    title: str
    timestamps: List[TimestampRange]  # Changed to match expected field name


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


def ranges_overlap(range1: TimestampRange, range2: TimestampRange) -> bool:
    """Check if two timestamp ranges overlap"""
    return (range1.start_time <= range2.end_time and
            range1.end_time >= range2.start_time)


def merge_overlapping_ranges(ranges: List[TimestampRange]) -> List[TimestampRange]:
    """Merge any overlapping timestamp ranges with improved label handling"""
    if not ranges:
        return []

    # Sort ranges by start time
    sorted_ranges = sorted(ranges, key=lambda x: x.start_time)
    merged = [sorted_ranges[0]]

    for current in sorted_ranges[1:]:
        last = merged[-1]
        if ranges_overlap(last, current):
            # Merge overlapping ranges
            last.end_time = max(last.end_time, current.end_time)

            # Handle labels
            if current.label:
                if last.label:
                    # If both ranges have labels, combine them only if they're different
                    if current.label != last.label:
                        last.label = f"{last.label} | {current.label}"
                else:
                    # If only the current range has a label, use it
                    last.label = current.label
        else:
            merged.append(current)

    return merged


# Movie Endpoints
@app.post("/movies/add-timestamps/")
def add_movie_timestamps(request: AddMovieRequest, db: Session = Depends(get_db)):
    existing_movie = db.query(Movie).filter(Movie.title == request.title).first()

    # Validate timestamp ranges
    for range_data in request.timestamps:
        if range_data.start_time >= range_data.end_time:
            raise HTTPException(
                status_code=400,
                detail="Start time must be less than end time"
            )

    if existing_movie:
        current_ranges = [TimestampRange(**ts) for ts in (existing_movie.timestamps or [])]
        new_ranges = current_ranges + request.timestamps

        # Merge overlapping ranges
        merged_ranges = merge_overlapping_ranges(new_ranges)

        # Update the movie with merged ranges
        existing_movie.timestamps = [ts.dict() for ts in merged_ranges]
        db.commit()
        db.refresh(existing_movie)

        return {
            "message": f"Timestamp ranges updated for movie '{existing_movie.title}'",
            "updated_timestamps": existing_movie.timestamps
        }

    new_movie = Movie(
        title=request.title,
        timestamps=[ts.dict() for ts in request.timestamps]
    )
    db.add(new_movie)
    db.commit()
    db.refresh(new_movie)
    return {"message": "Movie and timestamp ranges added successfully!"}


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
    # Validate timestamp ranges
    for range_data in request.timestamps:
        if range_data.start_time >= range_data.end_time:
            raise HTTPException(
                status_code=400,
                detail="Start time must be less than end time"
            )

    existing_episode = db.query(TVShow).filter(
        TVShow.show_name == request.show_name,
        TVShow.season == request.season,
        TVShow.episode_number == request.episode_number
    ).first()

    if existing_episode:
        current_ranges = [TimestampRange(**ts) for ts in (existing_episode.timestamps or [])]
        new_ranges = current_ranges + request.timestamps

        # Merge overlapping ranges
        merged_ranges = merge_overlapping_ranges(new_ranges)

        # Update the episode with merged ranges
        existing_episode.timestamps = [ts.dict() for ts in merged_ranges]
        db.commit()
        db.refresh(existing_episode)

        return {
            "message": f"Timestamp ranges updated for TV show '{existing_episode.show_name}' S{existing_episode.season}E{existing_episode.episode_number}",
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
    return {"message": "TV show episode and timestamp ranges added successfully!"}


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