from app.database import Column, Model, SurrogatePK, db

class GpsLocation(SurrogatePK, db.Model):
    __tablename__ = 'gps_locations'
    title = Column(db.String(100))
    lat = Column(db.Float())
    lon = Column(db.Float())
    range = Column(db.Float())
    is_home = Column(db.Boolean(), default = False)
