from app.database import Column, Model, SurrogatePK, db

class GpsPosition(SurrogatePK, db.Model):
    __tablename__ = 'gps_positions'
    added = Column(db.DateTime)
    device_id = Column(db.Integer)
    lat = Column(db.Float())
    lon = Column(db.Float())
    alt = Column(db.Float())
    accuracy = Column(db.Float())
    speed = Column(db.Float())
    battery = Column(db.Float())
    charging = Column(db.Boolean())
    provider = Column(db.String(50))
    address = Column(db.String(512))