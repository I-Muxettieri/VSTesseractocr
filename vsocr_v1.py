import os
import sys
import pytesseract
import vapoursynth as vs
import numpy as np
from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QLabel, QTextEdit, QFileDialog
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QPalette, QColor

# Ottieni il percorso della directory corrente
current_dir = os.path.dirname(os.path.realpath(__file__))
                           
# Check if tesseract is in the PATH or define tesseract_cmd with the full path to the Tesseract executable
pytesseract.pytesseract.tesseract_cmd = r'C:\\Users\\ryzen\\AppData\\Local\\Programs\\Tesseract-OCR\\tesseract.exe'

def set_dark_theme(app):
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    app.setPalette(palette)

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

class SubtitleExtractor(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        layout = QtWidgets.QVBoxLayout()

        # Status label
        self.status_label = QtWidgets.QLabel("Status: Ready")

        # File selector button
        self.file_selector = QtWidgets.QPushButton("Seleziona file o cartella")
        self.file_selector.setFixedSize(140, 25)
        self.file_selector.clicked.connect(self.select_file)
        self.file_selector.setStyleSheet("background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #404040")
        layout.addWidget(self.file_selector)

        # File path display
        self.file_path_display = QtWidgets.QTextEdit()
        self.file_path_display.setFixedSize(430, 25)
        self.file_path_display.setReadOnly(False)  # Set to True if you want to prevent user editing
        self.file_path_display.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_path_display.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_path_display.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        self.file_path_display.setStyleSheet("background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #404040")
        layout.addWidget(self.file_path_display)

        # Extract subtitles button
        extract_subtitle_button = QtWidgets.QPushButton("Estrai sottotitoli")
        extract_subtitle_button.clicked.connect(self.extractSubtitles)
        extract_subtitle_button.setStyleSheet("background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #404040")
        layout.addWidget(extract_subtitle_button)

        # Add the status label at the bottom
        layout.addWidget(self.status_label)

        # Set the layout and central widget
        main_widget = QtWidgets.QWidget()
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)

    def select_file(self):
        video_file, _ = QFileDialog.getOpenFileName(self, "Seleziona file video", "", "Video Files (*.mkv *.mp4 *.avi);;All Files (*)")
        if video_file:
            self.file_path_display.setText(video_file)
            self.video_path = video_file

    def extractSubtitles(self):
        # Extract subtitles when the button is clicked
        if hasattr(self, 'video_path') and self.video_path:
            self.status_label.setText("Status: Processing...")
            self.extraction_thread = ExtractSubtitlesThread(self.video_path)
            self.extraction_thread.update_status.connect(self.status_label.setText)
            self.extraction_thread.start()
        else:
            self.status_label.setText("Status: Seleziona prima un file")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    set_dark_theme(app)
    window = SubtitleExtractor()
    window.show()
    sys.exit(app.exec())