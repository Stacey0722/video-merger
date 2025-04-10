from app import app, db, VideoMaterial, MusicMaterial
import os

def init_db():
    with app.app_context():
        # 添加视频素材
        video_dir = os.path.join('uploads', 'videos')
        for filename in os.listdir(video_dir):
            if filename.endswith('.mp4'):
                filepath = os.path.join(video_dir, filename)
                video = VideoMaterial(
                    filename=filename,
                    filepath=filepath,
                    size=os.path.getsize(filepath)
                )
                db.session.add(video)
        
        # 添加音乐素材
        bgm_dir = os.path.join('uploads', 'bgm')
        for filename in os.listdir(bgm_dir):
            if filename.endswith('.mp3'):
                filepath = os.path.join(bgm_dir, filename)
                music = MusicMaterial(
                    filename=filename,
                    filepath=filepath,
                    size=os.path.getsize(filepath)
                )
                db.session.add(music)
        
        db.session.commit()
        print("数据库初始化完成！")

if __name__ == '__main__':
    init_db() 