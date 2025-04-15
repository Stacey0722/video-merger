import os
import random
import asyncio
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, CompositeAudioClip, TextClip, ColorClip, concatenate_audioclips, ImageClip
import logging
import numpy as np
import re
import json
from moviepy.config import change_settings
from PIL import Image, ImageDraw, ImageFont
import os

# 配置 ImageMagick
# os.environ['IMAGEMAGICK_BINARY'] = '/usr/bin/convert'
change_settings({"IMAGEMAGICK_BINARY": "/opt/homebrew/bin/convert"})


logger = logging.getLogger(__name__)

class VideoGenerator:
    def __init__(self, video_library_path, bgm_path, subtitle_length=12, font='STHeiti'):
        self.video_library_path = video_library_path
        self.bgm_path = bgm_path
        self.video_clips = []
        self.subtitle_clips = []
        self.subtitle_timings = []
        self.subtitle_length = subtitle_length
        self.font = font  # 添加字体属性

    def split_text_into_segments(self, text):
        """将文本切分成指定长度的段落"""
        segments = []
        for i in range(0, len(text), self.subtitle_length):
            segment = text[i:i+self.subtitle_length]
            segments.append(segment)
        return segments

    async def text_to_speech(self, text, voice, output_path):
        """将文本转换为语音"""
        try:
            # 保留原始文本（包含标点符号）用于语音生成
            original_text = text.strip()

            # 设置语音速度为1.2倍
            communicate = edge_tts.Communicate(original_text, voice, rate="+20%")  # +20% 相当于1.2倍速

            # 收集所有的时间戳
            word_timings = []
            current_word = ""
            word_start = 0

            # 首先收集每个字的时间戳
            async for chunk in communicate.stream():
                if chunk["type"] == "WordBoundary":
                    word_timings.append({
                        "text": chunk["text"],
                        "start": word_start / 10000000,
                        "end": chunk["offset"] / 10000000
                    })
                    word_start = chunk["offset"]

            # 保存语音文件
            await communicate.save(output_path)

            # 处理文本，按固定字数分段
            processed_timing_data = []
            current_segment = ""
            segment_start = None
            buffer = ""  # 用于存储未达到最小长度的文本
            buffer_start = None  # 缓冲区文本的开始时间

            min_segment_length = max(self.subtitle_length // 3, 4)  # 最小段落长度，至少4个字

            for i, word in enumerate(word_timings):
                if buffer:
                    buffer += word["text"]
                    if len(re.sub(r'[，。！？、："""]', '', buffer)) >= min_segment_length:
                        current_segment = buffer
                        segment_start = buffer_start
                        buffer = ""
                        buffer_start = None
                else:
                    current_segment += word["text"]
                    if segment_start is None:
                        segment_start = word["start"]

                # 当累积的文本达到指定长度，或遇到句末标点且当前段落超过最小长度时，或是最后一个字时，就进行分段
                is_end_punctuation = any(p in word["text"] for p in "。！？")
                is_last_word = i == len(word_timings) - 1
                current_length = len(re.sub(r'[，。！？、："""]', '', current_segment))

                if (current_length >= self.subtitle_length or
                    (is_end_punctuation and current_length >= min_segment_length) or
                    is_last_word):

                    # 移除标点符号用于显示
                    clean_segment = re.sub(r'[，。！？、："""]', '', current_segment)

                    # 如果当前段落超过指定长度，需要进一步分段
                    if len(clean_segment) > self.subtitle_length:
                        # 按指定长度切分，确保每段至少达到最小长度
                        for j in range(0, len(clean_segment), self.subtitle_length):
                            sub_segment = clean_segment[j:j+self.subtitle_length]
                            if len(sub_segment) < min_segment_length and j + self.subtitle_length < len(clean_segment):
                                continue  # 跳过过短的片段，将其与下一段合并

                            # 计算这部分文本对应的时间
                            sub_length = len(sub_segment)
                            total_length = len(clean_segment)
                            total_duration = word["end"] - segment_start
                            sub_duration = (total_duration * sub_length) / total_length

                            sub_start = segment_start + (j / len(clean_segment)) * total_duration
                            sub_end = sub_start + sub_duration

                            processed_timing_data.append({
                                "text": sub_segment,
                                "start": sub_start,
                                "end": sub_end - 0.1  # 稍微提前结束，避免字幕重叠
                            })
                    else:
                        if len(clean_segment) < min_segment_length and not is_last_word:
                            # 如果段落太短且不是最后一段，将其存入缓冲区
                            buffer = current_segment
                            buffer_start = segment_start
                        else:
                            processed_timing_data.append({
                                "text": clean_segment,
                                "start": segment_start,
                                "end": word["end"] - 0.1  # 稍微提前结束，避免字幕重叠
                            })

                    # 重置当前段落
                    if not buffer:
                        current_segment = ""
                        segment_start = None

            # 处理最后的缓冲区内容（如果有的话）
            if buffer:
                clean_buffer = re.sub(r'[，。！？、："""]', '', buffer)
                if clean_buffer:
                    processed_timing_data.append({
                        "text": clean_buffer,
                        "start": buffer_start,
                        "end": word_timings[-1]["end"] - 0.1
                    })

            self.subtitle_timings = processed_timing_data
            logger.info(f"语音生成成功: {output_path}")
            logger.info(f"获取到 {len(processed_timing_data)} 个时间戳")
            logger.info(f"时间戳数据: {json.dumps(processed_timing_data, ensure_ascii=False, indent=2)}")
            return output_path
        except Exception as e:
            logger.error(f"语音生成失败: {str(e)}")
            raise

    # def create_subtitle_clip(self, text, start_time, end_time, video_size):
    #     """创建字幕剪辑"""
    #     try:
    #         text = text.strip()

    #         logger.info(f"创建字幕: 文本='{text}', 开始时间={start_time}, 结束时间={end_time}, 视频尺寸={video_size}, 字体={self.font}")

    #         # 创建字幕文本（优化字幕参数）
    #         txt_clip = TextClip(
    #             text,
    #             fontsize=45,  # 字体大小
    #             color='white',  # 白色字体
    #             font=self.font,  # 使用用户选择的字体
    #             #stroke_color='white',  # 黑色描边
    #             #stroke_width=3,  # 增加描边宽度，使字幕更加清晰可见
    #             size=(video_size[0], video_size[1]),
    #             method='label',  # 使用caption方法以获得更好的渲染效果
    #             align='center',
    #             transparent=True
    #         ).set_position(('center', 0.8), relative=True)

    #         txt_clip = txt_clip.set_start(start_time)
    #         txt_clip = txt_clip.set_duration(end_time - start_time)

    #         return txt_clip
    #     except Exception as e:
    #         logger.error(f"创建字幕失败: {str(e)}")
    #         raise

    def create_subtitle_clip(self, text, start_time, end_time, video_size):
        """用 PIL 手动生成带描边的白色字幕 ImageClip"""
        try:
            # 字体和大小
            font_size = 45
            font_path = os.path.join(os.path.dirname(__file__), "fonts", "msyh.ttc") # macOS 下 STHeiti 字体路径
            font = ImageFont.truetype(font_path, font_size)

            # 创建透明背景图片
            img = Image.new("RGBA", video_size, (0, 0, 0, 0))  # RGBA透明背景
            draw = ImageDraw.Draw(img)

            # 测量文本尺寸并居中绘制
            text = text.strip()
            text_size = draw.textbbox((0, 0), text, font=font)
            text_width = text_size[2] - text_size[0]
            text_height = text_size[3] - text_size[1]
            position = ((video_size[0] - text_width) // 2, int(video_size[1] * 0.5))  # 居中偏下

            # 绘制黑色描边
            stroke_width = 3  # 描边宽度
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx*dx + dy*dy <= stroke_width*stroke_width:  # 圆形描边
                        draw.text(
                            (position[0] + dx, position[1] + dy),
                            text,
                            font=font,
                            fill=(0, 0, 0, 255)  # 黑色描边
                        )

            # 绘制白色文字
            draw.text(
                position,
                text,
                font=font,
                fill=(255, 255, 255, 255)  # 白色文字
            )

            # 转换为 ImageClip
            np_img = np.array(img)
            txt_clip = ImageClip(np_img, ismask=False)
            txt_clip = txt_clip.set_start(start_time).set_duration(end_time - start_time)
            txt_clip = txt_clip.set_position(('center', 'bottom'))

            return txt_clip
        except Exception as e:
            logger.error(f"创建字幕失败: {str(e)}")
            raise

    def split_text_into_sentences(self, text):
        """将文本分割成句子"""
        # 使用中文标点符号分割句子
        sentences = re.split(r'[。！？]', text)
        # 过滤空句子
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences

    def process_video(self, video_path, text=None):
        """处理视频：移除原声并调整时长"""
        try:
            video = VideoFileClip(video_path)
            # 移除原声
            video = video.without_audio()

            # 设置目标尺寸（降低分辨率以提高处理速度）
            target_height = 720  # 从1080p降至720p
            aspect_ratio = video.w / video.h
            target_width = int(target_height * aspect_ratio)

            # 确保宽度为偶数
            if target_width % 2 != 0:
                target_width += 1

            # 调整视频大小和帧率
            video = video.set_fps(25)  # 降低帧率以提高处理速度
            video = video.set_duration(video.duration)

            # 使用 PIL 的 BILINEAR 重采样方法（更快但质量稍低）
            from PIL import Image
            Image.Resampling = Image.Resampling.BILINEAR

            # 调整视频大小
            video = video.resize((target_width, target_height))

            return video
        except Exception as e:
            logger.error(f"处理视频时出错: {str(e)}")
            raise

    async def generate(self, text, output_path, voice="zh-CN-XiaoxiaoNeural"):
        """生成视频"""
        try:
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # 生成语音
            temp_dir = os.path.join(os.path.dirname(output_path), "temp")
            os.makedirs(temp_dir, exist_ok=True)
            narration_path = os.path.join(temp_dir, "narration.mp3")
            await self.text_to_speech(text, voice, narration_path)

            # 获取视频文件列表
            video_files = [os.path.join(self.video_library_path, f) for f in os.listdir(self.video_library_path)
                         if f.endswith(('.mp4', '.avi', '.mov'))]

            if not video_files:
                raise ValueError("没有找到视频文件")

            # 处理视频
            for video_path in video_files:
                video = self.process_video(video_path)
                self.video_clips.append(video)

            # 创建最终视频
            self.create_final_video(video_files, narration_path, output_path)

            # 清理临时文件
            try:
                os.remove(narration_path)
                os.rmdir(temp_dir)
            except Exception as e:
                logger.warning(f"清理临时文件失败: {str(e)}")

            return output_path
        except Exception as e:
            logger.error(f"生成视频失败: {str(e)}")
            raise

    def get_random_videos(self, count=3):
        """从视频库中随机获取视频"""
        try:
            # 获取视频库中的所有视频文件
            video_files = [f for f in os.listdir(self.video_library_path)
                          if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]

            if not video_files:
                raise Exception("视频库中没有找到视频文件！")

            # 验证视频文件
            valid_videos = []
            for video in video_files:
                try:
                    video_path = os.path.join(self.video_library_path, video)
                    # 尝试打开视频文件
                    clip = VideoFileClip(video_path)
                    # 检查视频是否可读
                    if clip.reader.nframes > 0:
                        valid_videos.append(video)
                    clip.close()
                except Exception as e:
                    logger.warning(f"视频文件 {video} 无效: {str(e)}")
                    continue

            if not valid_videos:
                raise Exception("没有找到有效的视频文件！")

            # 随机选择指定数量的视频
            selected_videos = random.sample(valid_videos, min(count, len(valid_videos)))
            logger.info(f"随机选择的视频: {selected_videos}")

            return [os.path.join(self.video_library_path, video) for video in selected_videos]
        except Exception as e:
            logger.error(f"随机选择视频失败: {str(e)}")
            raise

    def resize_video(self, clip, target_size):
        """调整视频尺寸"""
        try:
            # 检查视频是否有效
            if clip.reader.nframes == 0:
                raise Exception("视频帧数为0，可能是无效的视频文件")

            # 检查视频尺寸
            if clip.size[0] <= 0 or clip.size[1] <= 0:
                raise Exception("视频尺寸无效")

            # 调整视频尺寸
            resized_clip = clip.resize(width=target_size[0], height=target_size[1])

            # 验证调整后的视频
            if resized_clip.size[0] <= 0 or resized_clip.size[1] <= 0:
                raise Exception("调整后的视频尺寸无效")

            return resized_clip
        except Exception as e:
            logger.error(f"调整视频尺寸失败: {str(e)}")
            raise

    def create_final_video(self, video_paths, narration_path, output_path):
        """创建最终视频"""
        try:
            # 从视频库中随机选择视频
            video_paths = self.get_random_videos(len(video_paths))
            logger.info(f"使用视频路径: {video_paths}")

            # 加载视频片段
            video_clips = []
            for path in video_paths:
                try:
                    clip = VideoFileClip(path)
                    video_clips.append(clip)
                except Exception as e:
                    logger.error(f"加载视频片段失败 {path}: {str(e)}")
                    raise

            # 获取第一个视频的尺寸作为目标尺寸
            target_size = video_clips[0].size
            logger.info(f"目标视频尺寸: {target_size}")

            # 调整所有视频片段到相同尺寸
            video_clips = [self.resize_video(clip, target_size) for clip in video_clips]

            # 计算每个视频片段的持续时间
            total_duration = sum(clip.duration for clip in video_clips)

            # 加载语音
            narration = AudioFileClip(narration_path)
            narration_duration = narration.duration
            logger.info(f"语音时长: {narration_duration}秒")

            # 如果视频总长度超过语音长度，则循环播放视频
            if total_duration < narration_duration:
                repeat_times = int(narration_duration / total_duration) + 1
                video_clips = video_clips * repeat_times

            # 合并视频片段
            final_video = concatenate_videoclips(video_clips)

            # 截取视频以匹配语音长度
            final_video = final_video.subclip(0, narration_duration)

            # 加载背景音乐
            bgm = AudioFileClip(self.bgm_path)

            # 调整背景音乐音量
            bgm = bgm.volumex(0.3)

            # 循环背景音乐以匹配视频长度
            if bgm.duration < narration_duration:
                repeat_times = int(narration_duration / bgm.duration) + 1
                bgm_clips = [bgm] * repeat_times
                bgm = concatenate_audioclips(bgm_clips)

            # 截取背景音乐以匹配视频长度
            bgm = bgm.subclip(0, narration_duration)

            # 合并音频
            final_audio = CompositeAudioClip([narration, bgm])

            # 创建字幕剪辑
            subtitle_clips = []
            for timing in self.subtitle_timings:
                subtitle_clip = self.create_subtitle_clip(
                    timing["text"],
                    timing["start"],
                    timing["end"],
                    final_video.size
                )
                subtitle_clips.append(subtitle_clip)

            logger.info(f"创建了 {len(subtitle_clips)} 个字幕剪辑")

            # 创建字幕层，使用交叉淡入淡出效果
            subtitle_layer = CompositeVideoClip(subtitle_clips, use_bgclip=False)
            logger.info(f"字幕层创建成功，尺寸: {subtitle_layer.size}")

            # 加载水印图片
            watermark_path = os.path.join(os.getcwd(), 'uploads', 'watermarks', '20250317-181646.png')
            if not os.path.exists(watermark_path):
                logger.warning(f"水印文件不存在: {watermark_path}，跳过水印添加")
                # 不添加水印，直接使用原视频
                main_video = CompositeVideoClip([final_video, subtitle_layer])
            else:
                watermark = ImageClip(watermark_path)
                watermark = watermark.set_duration(narration_duration)  # 设置水印持续时间
                watermark = watermark.resize(final_video.size)  # 设置水印尺寸与视频一致
                watermark = watermark.set_position(('center', 'center'))  # 设置水印位置居中
                # 将视频、字幕层和水印层组合，确保字幕在最上层
                main_video = CompositeVideoClip([final_video, watermark, subtitle_layer])

            # 加载尾板视频
            endboard_path = os.path.join(os.getcwd(), 'uploads', 'endboards', '1.mp4')
            if not os.path.exists(endboard_path):
                logger.warning(f"尾板视频不存在: {endboard_path}，跳过尾板添加")
                final_video = main_video
                final_audio = final_audio
            else:
                endboard = VideoFileClip(endboard_path)
                endboard = endboard.resize(final_video.size)  # 设置尾板尺寸与视频一致
                endboard_duration = endboard.duration
                logger.info(f"尾板视频时长: {endboard_duration}秒")

                # 将主视频和尾板视频连接
                final_video = concatenate_videoclips([main_video, endboard])

                # 创建尾板音频
                endboard_audio = endboard.audio

                # 更新音频时长并合并音频
                final_audio = final_audio.set_duration(main_video.duration)
                final_audio = CompositeAudioClip([final_audio, endboard_audio.set_start(main_video.duration)])

            # 设置音频
            final_video = final_video.set_audio(final_audio)

            logger.info(f"最终视频尺寸: {final_video.size}")

            # 写入最终视频
            final_video.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                fps=25,
                preset='ultrafast',
                threads=8,
                bitrate='3000k',
                ffmpeg_params=[
                    '-tune', 'zerolatency',
                    '-movflags', '+faststart',
                    '-bf', '0',
                    '-g', '25',
                    '-sc_threshold', '0'
                ]
            )

            # 关闭所有剪辑
            for clip in video_clips:
                clip.close()
            narration.close()
            bgm.close()
            endboard.close()
            final_video.close()

            return output_path
        except Exception as e:
            logger.error(f"创建最终视频失败: {str(e)}")
            raise

    async def create_final_video_with_existing_audio(self, video_paths, narration_path, output_path):
        """使用已存在的语音和字幕时间戳创建最终视频"""
        try:
            # 验证参数
            if not video_paths or len(video_paths) == 0:
                raise ValueError("未提供视频文件路径")

            if not os.path.exists(narration_path):
                raise ValueError(f"语音文件不存在: {narration_path}")

            if not os.path.exists(self.bgm_path):
                raise ValueError(f"背景音乐文件不存在: {self.bgm_path}")

            # 加载视频片段
            video_clips = []
            for path in video_paths:
                try:
                    clip = VideoFileClip(path)
                    video_clips.append(clip)
                except Exception as e:
                    logger.error(f"加载视频片段失败 {path}: {str(e)}")
                    raise

            # 获取第一个视频的尺寸作为目标尺寸
            target_size = video_clips[0].size
            logger.info(f"目标视频尺寸: {target_size}")

            # 调整所有视频片段到相同尺寸
            video_clips = [self.resize_video(clip, target_size) for clip in video_clips]

            # 计算每个视频片段的持续时间
            total_duration = sum(clip.duration for clip in video_clips)

            # 加载语音
            narration = AudioFileClip(narration_path)
            narration_duration = narration.duration
            logger.info(f"语音时长: {narration_duration}秒")

            # 如果视频总长度超过语音长度，则循环播放视频
            if total_duration < narration_duration:
                repeat_times = int(narration_duration / total_duration) + 1
                video_clips = video_clips * repeat_times

            # 合并视频片段
            final_video = concatenate_videoclips(video_clips)

            # 截取视频以匹配语音长度
            final_video = final_video.subclip(0, narration_duration)

            # 加载背景音乐
            bgm = AudioFileClip(self.bgm_path)

            # 调整背景音乐音量
            bgm = bgm.volumex(0.3)

            # 循环背景音乐以匹配视频长度
            if bgm.duration < narration_duration:
                repeat_times = int(narration_duration / bgm.duration) + 1
                bgm_clips = [bgm] * repeat_times
                bgm = concatenate_audioclips(bgm_clips)

            # 截取背景音乐以匹配视频长度
            bgm = bgm.subclip(0, narration_duration)

            # 合并音频
            final_audio = CompositeAudioClip([narration, bgm])

            # 创建字幕剪辑
            subtitle_clips = []
            for timing in self.subtitle_timings:
                subtitle_clip = self.create_subtitle_clip(
                    timing["text"],
                    timing["start"],
                    timing["end"],
                    final_video.size
                )
                subtitle_clips.append(subtitle_clip)

            logger.info(f"创建了 {len(subtitle_clips)} 个字幕剪辑")

            # 创建字幕层，使用交叉淡入淡出效果
            subtitle_layer = CompositeVideoClip(subtitle_clips, use_bgclip=False)
            logger.info(f"字幕层创建成功，尺寸: {subtitle_layer.size}")

            # 加载水印图片
            watermark_path = os.path.join(os.getcwd(), 'uploads', 'watermarks', '20250317-181646.png')
            if not os.path.exists(watermark_path):
                logger.warning(f"水印文件不存在: {watermark_path}，跳过水印添加")
                # 不添加水印，直接使用原视频
                main_video = CompositeVideoClip([final_video, subtitle_layer])
            else:
                watermark = ImageClip(watermark_path)
                watermark = watermark.set_duration(narration_duration)  # 设置水印持续时间
                watermark = watermark.resize(final_video.size)  # 设置水印尺寸与视频一致
                watermark = watermark.set_position(('center', 'center'))  # 设置水印位置居中
                # 将视频、字幕层和水印层组合，确保字幕在最上层
                main_video = CompositeVideoClip([final_video, watermark, subtitle_layer])

            # 加载尾板视频
            endboard_path = os.path.join(os.getcwd(), 'uploads', 'endboards', '1.mp4')
            if not os.path.exists(endboard_path):
                logger.warning(f"尾板视频不存在: {endboard_path}，跳过尾板添加")
                final_video = main_video
                final_audio = final_audio
            else:
                endboard = VideoFileClip(endboard_path)
                endboard = endboard.resize(final_video.size)  # 设置尾板尺寸与视频一致
                endboard_duration = endboard.duration
                logger.info(f"尾板视频时长: {endboard_duration}秒")

                # 将主视频和尾板视频连接
                final_video = concatenate_videoclips([main_video, endboard])

                # 创建尾板音频
                endboard_audio = endboard.audio

                # 更新音频时长并合并音频
                final_audio = final_audio.set_duration(main_video.duration)
                final_audio = CompositeAudioClip([final_audio, endboard_audio.set_start(main_video.duration)])

            # 设置音频
            final_video = final_video.set_audio(final_audio)

            logger.info(f"最终视频尺寸: {final_video.size}")

            # 写入最终视频
            final_video.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                fps=25,
                preset='ultrafast',
                threads=8,
                bitrate='3000k',
                ffmpeg_params=[
                    '-tune', 'zerolatency',
                    '-movflags', '+faststart',
                    '-bf', '0',
                    '-g', '25',
                    '-sc_threshold', '0'
                ]
            )

            # 关闭所有剪辑
            for clip in video_clips:
                clip.close()
            narration.close()
            bgm.close()
            endboard.close()
            final_video.close()

            return output_path
        except Exception as e:
            logger.error(f"创建最终视频失败: {str(e)}")
            raise

async def main():
    parser = argparse.ArgumentParser(description='视频生成工具')
    parser.add_argument('text_file', help='包含小说文本的文件路径')
    parser.add_argument('video_library', help='视频素材库目录路径')
    parser.add_argument('bgm_file', help='背景音乐文件路径')
    parser.add_argument('output_file', help='输出视频文件路径')
    parser.add_argument('--voice', default='zh-CN-XiaoxiaoNeural', help='语音合成的声音')

    args = parser.parse_args()

    # 检查输入文件是否存在
    if not all(os.path.exists(path) for path in [args.text_file, args.video_library, args.bgm_file]):
        print("错误：输入文件或目录不存在！")
        return

    # 读取文本文件
    with open(args.text_file, 'r', encoding='utf-8') as f:
        text = f.read()

    # 创建临时目录
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # 初始化视频生成器
        generator = VideoGenerator(args.video_library, args.bgm_file)

        # 生成视频
        output_path = await generator.generate(text, args.output_file, args.voice)
        print(f"视频已成功生成并保存到: {output_path}")

    except Exception as e:
        print(f"处理过程中出错: {str(e)}")
    finally:
        # 清理临时文件
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                os.remove(os.path.join(temp_dir, file))
            os.rmdir(temp_dir)

if __name__ == '__main__':
    asyncio.run(main())
