import os
import logging
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from video_merger import VideoGenerator
import asyncio
from datetime import datetime
import traceback
import re
import shutil
from models import db, VideoMaterial, MusicMaterial, GeneratedVideo
import random
from urllib.parse import quote, unquote

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///video_merger.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['VIDEO_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], 'videos')
app.config['BGM_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], 'bgm')
app.config['OUTPUT_FOLDER'] = 'output'
app.config['VIDEO_LIBRARY_FOLDER'] = 'video_library'

# 全局进度跟踪变量
process_status = {
    'progress': 0,
    'stage': '准备中...',
    'task_id': None
}

# 初始化数据库
db.init_app(app)

# 确保必要的目录存在
for folder in [app.config['UPLOAD_FOLDER'], app.config['VIDEO_FOLDER'], app.config['BGM_FOLDER'], app.config['OUTPUT_FOLDER']]:
    os.makedirs(folder, exist_ok=True)
    logger.info(f"确保目录存在: {folder}")

# 确保视频素材库目录存在
os.makedirs(app.config['VIDEO_LIBRARY_FOLDER'], exist_ok=True)

# 确保各类别音乐目录存在
for category in ['male', 'modern_sweet', 'modern_urban', 'ancient']:
    category_path = os.path.join(app.config['BGM_FOLDER'], category)
    os.makedirs(category_path, exist_ok=True)
    logger.info(f"确保音乐分类目录存在: {category_path}")

# 允许的文件类型
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def preprocess_text(text):
    """预处理文本，移除HTML标签和特殊字符"""
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', '', text)
    # 移除特殊字符，保留中文标点
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9，。！？、]', '', text)
    return text.strip()

@app.route('/')
def index():
    """渲染主页"""
    try:
        videos = VideoMaterial.query.all()
        music = MusicMaterial.query.all()
        return render_template('index.html', videos=videos, music=music)
    except Exception as e:
        logger.error(f'访问首页时出错: {str(e)}')
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/video_library')
def video_library():
    """视频素材库页面"""
    try:
        # 获取视频素材库中的所有视频文件
        video_files = [f for f in os.listdir(app.config['VIDEO_LIBRARY_FOLDER'])
                      if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
        return render_template('video_library.html', videos=video_files)
    except Exception as e:
        logger.error(f"访问视频素材库失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/music_library')
def music_library():
    """音乐素材库页面"""
    try:
        # 获取所有分类的音乐文件
        music_files = []
        for category in ['male', 'modern_sweet', 'modern_urban', 'ancient']:
            category_path = os.path.join(app.config['BGM_FOLDER'], category)
            
            if os.path.exists(category_path):
                files = [f for f in os.listdir(category_path)
                        if f.lower().endswith(('.mp3', '.wav', '.ogg'))]
                
                for filename in files:
                    # 解码文件名
                    decoded_filename = unquote(filename)
                    music_files.append({
                        'filename': decoded_filename,
                        'category': category
                    })
        
        return render_template('music_library.html', music_files=music_files)
    except Exception as e:
        logger.error(f"访问音乐素材库失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload_video', methods=['POST'])
def upload_video():
    """上传视频到素材库"""
    try:
        if 'video' not in request.files:
            return jsonify({'error': '没有选择文件'}), 400
        
        file = request.files['video']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        if file and allowed_file(file.filename, {'mp4', 'avi', 'mov', 'mkv'}):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['VIDEO_LIBRARY_FOLDER'], filename))
            return jsonify({'message': '视频上传成功'})
        else:
            return jsonify({'error': '不支持的文件类型'}), 400
    except Exception as e:
        logger.error(f"上传视频失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/delete_video/<filename>', methods=['DELETE'])
def delete_video(filename):
    """删除视频素材"""
    try:
        file_path = os.path.join(app.config['VIDEO_LIBRARY_FOLDER'], filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'message': '视频删除成功'})
        else:
            return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        logger.error(f"删除视频失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload_material', methods=['POST'])
def upload_material():
    """上传视频或音乐素材"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有文件被上传'}), 400
        
        file = request.files['file']
        material_type = request.form.get('type', 'video')
        
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        # 检查文件类型
        allowed_extensions = ALLOWED_VIDEO_EXTENSIONS if material_type == 'video' else ALLOWED_AUDIO_EXTENSIONS
        if not allowed_file(file.filename, allowed_extensions):
            return jsonify({'error': '不支持的文件类型'}), 400
        
        # 保存文件
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        if material_type == 'video':
            filepath = os.path.join(app.config['VIDEO_FOLDER'], filename)
            model = VideoMaterial
        else:
            filepath = os.path.join(app.config['BGM_FOLDER'], filename)
            model = MusicMaterial
        
        file.save(filepath)
        
        # 创建数据库记录
        material = model(
            filename=file.filename,
            filepath=filepath,
            size=os.path.getsize(filepath)
        )
        db.session.add(material)
        db.session.commit()
        
        return jsonify({
            'message': '文件上传成功',
            'filename': file.filename,
            'id': material.id
        })
        
    except Exception as e:
        logger.error(f"上传素材时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_materials', methods=['GET'])
def get_materials():
    """获取所有素材列表"""
    try:
        material_type = request.args.get('type', 'video')
        if material_type == 'video':
            materials = VideoMaterial.query.all()
        else:
            materials = MusicMaterial.query.all()
        
        return jsonify([{
            'id': m.id,
            'filename': m.filename,
            'created_at': m.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'size': m.size
        } for m in materials])
        
    except Exception as e:
        logger.error(f"获取素材列表时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/process_progress', methods=['GET'])
def get_progress():
    """获取当前处理进度"""
    global process_status
    return jsonify(process_status)

def update_progress(progress, stage):
    """更新处理进度"""
    global process_status
    process_status['progress'] = progress
    process_status['stage'] = stage
    logger.info(f"进度更新: {progress}%, 阶段: {stage}")

@app.route('/generate', methods=['POST'])
def generate():
    """生成视频接口"""
    try:
        # 重置进度
        global process_status
        process_status = {
            'progress': 0,
            'stage': '准备中...',
            'task_id': datetime.now().strftime("%Y%m%d%H%M%S")
        }
        
        text = request.form.get('text')
        voice = request.form.get('voice')
        video_count = int(request.form.get('video_count', 1))
        novel_type = request.form.get('novel_type', 'male')  # 获取小说类型
        subtitle_length = int(request.form.get('subtitle_length', 12))  # 获取字幕长度，默认为12
        font = request.form.get('font', 'STHeiti')  # 获取字体参数
        
        if not text:
            return jsonify({'error': '请提供文本内容'}), 400
        
        if video_count < 1:
            return jsonify({'error': '视频数量必须大于等于1'}), 400
            
        update_progress(5, "正在初始化...")
            
        # 创建临时目录
        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # 生成语音文件名
        narration_path = os.path.join(temp_dir, "narration.mp3")
        
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_files = []
        
        update_progress(10, "正在分析文本...")
        
        # 根据小说类型选择对应的音乐素材目录
        bgm_category_path = os.path.join(app.config['BGM_FOLDER'], novel_type)
        
        # 获取分类目录下的所有音乐文件
        bgm_files = []
        if os.path.exists(bgm_category_path):
            bgm_files = [f for f in os.listdir(bgm_category_path) 
                      if f.lower().endswith(tuple(ALLOWED_AUDIO_EXTENSIONS))]
        
        # 检查是否有可用的背景音乐
        if not bgm_files:
            logger.warning(f"未找到'{novel_type}'类型的背景音乐，请先上传")
            return jsonify({'error': f"未找到'{novel_type}'类型的背景音乐，请先上传"}), 400
        
        update_progress(15, "正在生成语音...")
        
        # 一次性生成语音和字幕
        first_generator = VideoGenerator(os.path.join(os.getcwd(), app.config['VIDEO_LIBRARY_FOLDER']), "", subtitle_length=subtitle_length, font=font)  # 添加字体参数
        
        # 生成语音和字幕
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(first_generator.text_to_speech(text, voice, narration_path))
        subtitle_timings = first_generator.subtitle_timings
        
        update_progress(30, "语音生成完成，正在处理字幕...")

        # 为每个请求的视频生成不同的素材组合
        total_videos = video_count
        for i in range(video_count):
            current_video = i + 1
            progress_percent = 30 + (i / total_videos) * 60  # 从30%到90%的进度
            update_progress(
                int(progress_percent), 
                f"正在生成视频 {current_video}/{total_videos}..."
            )
            
            output_file = os.path.join(app.config['OUTPUT_FOLDER'], f"{timestamp}-{i+1}.mp4")
            
            # 随机选择一个背景音乐文件
            random_bgm = random.choice(bgm_files)
            bgm_path = os.path.join(bgm_category_path, random_bgm)
            logger.info(f"选择的背景音乐: {bgm_path}")
            
            # 生成视频
            generator = VideoGenerator(os.path.join(os.getcwd(), app.config['VIDEO_LIBRARY_FOLDER']), bgm_path, subtitle_length=subtitle_length, font=font)  # 添加字体参数
            generator.subtitle_timings = subtitle_timings  # 使用已生成的字幕时间戳
            
            update_progress(
                int(progress_percent + 10), 
                f"视频 {current_video}/{total_videos}: 正在选择视频素材..."
            )
            
            # 生成最终视频
            random_video_paths = generator.get_random_videos(3)  # 随机选择3个视频
            
            update_progress(
                int(progress_percent + 20), 
                f"视频 {current_video}/{total_videos}: 正在合成视频..."
            )
            
            loop.run_until_complete(generator.create_final_video_with_existing_audio(
                random_video_paths, 
                narration_path, 
                output_file
            ))
            
            output_files.append(os.path.basename(output_file))
        
        # 关闭事件循环
        loop.close()
        
        update_progress(95, "正在清理临时文件...")
        
        # 清理临时文件
        try:
            # 删除临时文件
            if os.path.exists(narration_path):
                os.remove(narration_path)
            
            # 删除临时目录中的所有文件
            if os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    file_path = os.path.join(temp_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                # 删除临时目录
                try:
                    os.rmdir(temp_dir)
                except Exception as e:
                    logger.warning(f"删除临时目录失败: {str(e)}")
        except Exception as e:
            logger.warning(f"清理临时文件失败: {str(e)}")
        
        update_progress(100, "处理完成!")
        
        return jsonify({
            'message': f'成功生成 {len(output_files)} 个视频',
            'files': output_files
        })
    except Exception as e:
        logger.error(f"生成视频失败: {str(e)}")
        update_progress(-1, f"处理失败: {str(e)}")
        return jsonify({'error': f'生成视频失败: {str(e)}'}), 500

def select_bgm_by_type(novel_type):
    """根据小说类型选择合适的背景音乐"""
    # 获取对应类型的音乐列表
    bgm_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'bgm')
    type_folder = os.path.join(bgm_folder, novel_type)
    
    # 如果存在该类型的专用文件夹，从中选择音乐
    if os.path.exists(type_folder) and os.listdir(type_folder):
        bgm_files = [f for f in os.listdir(type_folder) 
                    if f.lower().endswith(('.mp3', '.wav', '.ogg'))]
        if bgm_files:
            # 随机选择一个音乐文件
            selected_bgm = random.choice(bgm_files)
            return os.path.join(type_folder, selected_bgm)
    
    # 如果没有找到专用音乐，返回默认音乐
    default_bgm = os.path.join(bgm_folder, 'default.mp3')
    if os.path.exists(default_bgm):
        return default_bgm
    
    # 如果默认音乐也不存在，尝试返回bgm文件夹中的第一个音乐文件
    all_bgm_files = [f for f in os.listdir(bgm_folder) 
                   if os.path.isfile(os.path.join(bgm_folder, f)) and 
                   f.lower().endswith(('.mp3', '.wav', '.ogg'))]
    if all_bgm_files:
        return os.path.join(bgm_folder, all_bgm_files[0])
    
    # 如果什么都没找到，返回None，让系统自行处理
    return None

@app.route('/download/<filename>')
def download_file(filename):
    """下载生成的视频"""
    try:
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_file(
                file_path,
                as_attachment=True
            )
        else:
            return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        logger.error(f"下载文件时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/delete_material/<int:material_id>', methods=['DELETE'])
def delete_material(material_id):
    """删除素材"""
    try:
        material_type = request.args.get('type', 'video')
        if material_type == 'video':
            material = VideoMaterial.query.get_or_404(material_id)
        else:
            material = MusicMaterial.query.get_or_404(material_id)
        
        # 删除文件
        if os.path.exists(material.filepath):
            os.remove(material.filepath)
        
        # 删除数据库记录
        db.session.delete(material)
        db.session.commit()
        
        return jsonify({'message': '素材删除成功'})
        
    except Exception as e:
        logger.error(f"删除素材时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload_music', methods=['POST'])
def upload_music():
    """上传音乐到素材库"""
    try:
        if 'music' not in request.files:
            return jsonify({'error': '没有选择文件'}), 400
        
        music_file = request.files['music']
        category = request.form.get('category', 'modern_urban')  # 默认为现言都市
        
        if music_file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        if music_file and allowed_file(music_file.filename, ALLOWED_AUDIO_EXTENSIONS):
            # 对文件名进行 URL 编码
            filename = quote(music_file.filename)
            
            # 确保目录存在
            category_path = os.path.join(app.config['BGM_FOLDER'], category)
            os.makedirs(category_path, exist_ok=True)
            
            music_file.save(os.path.join(category_path, filename))
            return jsonify({'message': '音乐上传成功'})
        else:
            return jsonify({'error': '不支持的文件类型'}), 400
    except Exception as e:
        logger.error(f"上传音乐失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/delete_music/<category>/<filename>', methods=['DELETE'])
def delete_music(category, filename):
    """删除音乐素材"""
    try:
        if category not in ['male', 'modern_sweet', 'modern_urban', 'ancient']:
            return jsonify({'error': '无效的分类'}), 400
            
        file_path = os.path.join(app.config['BGM_FOLDER'], category, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'message': '音乐删除成功'})
        else:
            return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        logger.error(f"删除音乐失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    try:
        with app.app_context():
            db.create_all()
        app.run(host='0.0.0.0', port=5001, debug=True)
    except Exception as e:
        logger.error(f'启动应用时出错: {str(e)}')
        logger.error(traceback.format_exc()) 