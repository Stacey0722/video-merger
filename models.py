from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class VideoMaterial(db.Model):
    """视频素材模型"""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    duration = db.Column(db.Float)  # 视频时长（秒）
    size = db.Column(db.Integer)     # 文件大小（字节）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime)  # 最后使用时间
    use_count = db.Column(db.Integer, default=0)  # 使用次数

class MusicMaterial(db.Model):
    """音乐素材模型"""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    duration = db.Column(db.Float)  # 音乐时长（秒）
    size = db.Column(db.Integer)     # 文件大小（字节）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime)  # 最后使用时间
    use_count = db.Column(db.Integer, default=0)  # 使用次数

class GeneratedVideo(db.Model):
    """生成的视频记录"""
    id = db.Column(db.Integer, primary_key=True)
    output_filename = db.Column(db.String(255), nullable=False)
    output_filepath = db.Column(db.String(255), nullable=False)
    text_content = db.Column(db.Text)
    voice_type = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    duration = db.Column(db.Float)  # 视频时长（秒）
    size = db.Column(db.Integer)     # 文件大小（字节） 