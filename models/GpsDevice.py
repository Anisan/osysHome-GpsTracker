from app.database import Column, Model, SurrogatePK, db

class GpsDevice(SurrogatePK, db.Model):
    __tablename__ = 'gps_devices'
    title = Column(db.String(100))
    device_id = Column(db.String(100))
    linked_object = Column(db.String(255))
    lat = Column(db.Float())
    lon = Column(db.Float())
    updated = Column(db.DateTime)
    
