import os
import sys
import pytesseract
import vapoursynth as vs
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QFileDialog, QVBoxLayout, QWidget, QLabel
from PyQt6.QtCore import QThread, pyqtSignal

# Ottieni il percorso della directory corrente
current_dir = os.path.dirname(os.path.realpath(__file__))
                           
# Check if tesseract is in the PATH or define tesseract_cmd with the full path to the Tesseract executable
pytesseract.pytesseract.tesseract_cmd = r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'

core = vs.core
ffms2 = os.path.join(current_dir, 'vapoursynth', 'vapoursynth64', 'plugins', 'ffms2')
core.std.LoadPlugin(path=ffms2)

def detect_subtitles(frame):
    # Use numpy to handle frame data
    frame_array = np.asarray(frame[0])
    # Use Pytesseract to recognize text directly from the numpy array
    subtitle_text = pytesseract.image_to_string(frame_array, lang='ita')
    return subtitle_text

def milliseconds_to_srt_time(milliseconds):
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def write_subtitle_to_srt(srt_file, index, start_time, end_time, subtitle_text):
    start_time_str = milliseconds_to_srt_time(start_time)
    end_time_str = milliseconds_to_srt_time(end_time)
    srt_file.write(f"{index}\n{start_time_str} --> {end_time_str}\n{subtitle_text}\n\n")

class ExtractSubtitlesThread(QThread):
    update_status = pyqtSignal(str)

    def __init__(self, video_path):
        super().__init__()
        self.video_path = video_path

    def run(self):
        srt_file_path = os.path.splitext(self.video_path)[0] + ".srt"
        # Carica il video e convertilo in RGB
        video = core.ffms2.Source(self.video_path)
        if video.format.color_family != vs.RGB:
            video = core.resize.Point(clip=video, format=vs.RGB24)
        prev_subs = None
        all_subtitles = []

        with open(srt_file_path, "w", encoding="utf-8") as srt_file:
            frame_num = video.num_frames

            for n in range(frame_num):
                frame = video.get_frame(n)
                frame_time = int(frame.props['_DurationNum'] * 1000 / frame.props['_DurationDen'])
                subtitle_text = detect_subtitles(frame)
                start_time = n * frame_time
                end_time = start_time + frame_time

                # Check if the subtitle is the same as the previous one to avoid duplicates
                if subtitle_text and (not prev_subs or subtitle_text != prev_subs[2]):
                    write_subtitle_to_srt(srt_file, len(all_subtitles) + 1, start_time, end_time, subtitle_text)
                    all_subtitles.append((start_time, end_time, subtitle_text))

                prev_subs = (start_time, end_time, subtitle_text) if subtitle_text else prev_subs

        self.update_status.emit(f"Status: Subtitles extracted and saved to {srt_file_path}.")

class SubtitleExtractor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Subtitle Extractor")
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)

        self.status_label = QLabel("Status: Ready")
        select_video_button = QPushButton("Select Video")
        select_video_button.clicked.connect(self.selectVideo)
        extract_subtitle_button = QPushButton("Extract Subtitles")
        extract_subtitle_button.clicked.connect(self.extractSubtitles)

        layout.addWidget(select_video_button)
        layout.addWidget(extract_subtitle_button)
        layout.addWidget(self.status_label)

        self.setCentralWidget(main_widget)

    def selectVideo(self):
        video_file, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Video Files (*.mkv *.mp4 *.avi);;All Files (*)")
        if video_file:
            self.video_path = video_file

    def extractSubtitles(self):
        if hasattr(self, 'video_path'):
            self.status_label.setText("Status: Processing...")
            self.extraction_thread = ExtractSubtitlesThread(self.video_path)
            self.extraction_thread.update_status.connect(self.status_label.setText)
            self.extraction_thread.start()
        else:
            self.status_label.setText("Status: Please select a video first.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SubtitleExtractor()
    window.show()
    sys.exit(app.exec())
