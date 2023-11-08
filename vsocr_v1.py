import os
import sys
import numpy as np
from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QLabel, QTextEdit, QFileDialog
from PyQt6.QtCore import Qt,QThread, pyqtSignal
from PyQt6.QtGui import QPalette, QColor
from google.cloud import vision
import vapoursynth as vs
from PIL import Image
import io

# Configura qui il percorso al file delle credenziali, se necessario
# os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'path/to/your/credentials.json'

# Ottieni il percorso della directory corrente
current_dir = os.path.dirname(os.path.realpath(__file__))

# Configurazione iniziale di VapourSynth
core = vs.core
ffms2 = os.path.join(current_dir, 'vapoursynth', 'vapoursynth64', 'plugins', 'ffms2')
core.std.LoadPlugin(path=ffms2)

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

def preprocess_image(image, hex_color):
    # Controlla se hex_color è un colore esadecimale valido
    if len(hex_color) != 6 or not all(c in '0123456789ABCDEFabcdef' for c in hex_color):
        return image  # Se non è valido, restituisci l'immagine originale

    # Converti il colore esadecimale in RGB
    color = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    # Converte l'array numpy in un'immagine PIL
    pil_image = Image.fromarray(image)

    # Ottieni i dati dell'immagine come una lista di tuple
    data = list(pil_image.getdata())

    # Crea una nuova lista di dati per la nuova immagine
    new_data = []
    for item in data:
        # Se il colore del pixel corrisponde al colore specificato, aggiungilo alla nuova immagine
        if item == color:
            new_data.append(item)
        else:
            # Altrimenti, rendi il pixel trasparente (per le immagini RGBA) o bianco (per le immagini RGB)
            new_data.append((0, 0, 0, 0) if len(item) == 4 else (255, 255, 255))

    # Crea una nuova immagine con lo stesso formato e dimensioni dell'immagine originale
    new_image = Image.new(pil_image.mode, pil_image.size)

    # Aggiorna i dati della nuova immagine
    new_image.putdata(new_data)
    cv2.imwrite(f'temp/processed_frame_{new_image}.png', image)
    return new_image

def milliseconds_to_srt_time(milliseconds):
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def write_subtitle_to_srt(srt_file, index, start_time, end_time, subtitle_text):
    start_time_str = milliseconds_to_srt_time(start_time)
    end_time_str = milliseconds_to_srt_time(end_time)
    srt_file.write(f"{index}\n{start_time_str} --> {end_time_str}\n{subtitle_text}\n\n")

def detect_text_with_google_vision(image):
    client = vision.ImageAnnotatorClient()
    content = io.BytesIO()
    image.save(content, format='PNG')
    content = content.getvalue()
    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations
    return texts[0].description if texts else ''

# Thread per l'estrazione dei sottotitoli
class ExtractSubtitlesThread(QThread):
    update_status = pyqtSignal(str)
    update_progress = pyqtSignal(int)

    def __init__(self, video_path, hex_color):
        super().__init__()
        self.video_path = video_path
        self.hex_color = hex_color

    def run(self):
        srt_file_path = os.path.splitext(self.video_path)[0] + ".srt"
        video = vs.core.ffms2.Source(source=self.video_path)
        if video.format.color_family != vs.RGB:
            video = vs.core.resize.Point(clip=video, format=vs.RGB24)

        prev_subtitle_text = ''
        prev_end_time = -1
        subtitle_index = 1

        with open(srt_file_path, "w", encoding="utf-8") as srt_file:
            for n in range(video.num_frames):
                frame = video.get_frame(n)
                frame_array = np.array(frame[0].resize.Point(format=vs.GRAY8, matrix_in_s='709', matrix_s='170m'))
                image = Image.fromarray(frame_array)
                subtitle_text = detect_text_with_google_vision(image)

                frame_time = int(frame.props['_DurationNum'] * 1000 / frame.props['_DurationDen'])
                start_time = n * frame_time
                end_time = start_time + frame_time

                if subtitle_text == prev_subtitle_text:
                    prev_end_time = end_time
                else:
                    if prev_subtitle_text:
                        write_subtitle_to_srt(srt_file, subtitle_index, start_time, prev_end_time, prev_subtitle_text)
                        subtitle_index += 1
                    prev_subtitle_text = subtitle_text
                    prev_end_time = end_time

                # Update the progress via signal
                self.update_progress.emit(n / video.num_frames * 100)

            # Ensure the last subtitle is written out
            if prev_subtitle_text:
                write_subtitle_to_srt(srt_file, subtitle_index, start_time, prev_end_time, prev_subtitle_text)

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
        self.file_selector.setFixedSize(140, 30)
        self.file_selector.clicked.connect(self.select_file)
        self.file_selector.setStyleSheet("background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #404040")
        layout.addWidget(self.file_selector)

        # File path display
        self.file_path_display = QtWidgets.QTextEdit()
        self.file_path_display.setFixedSize(430, 30)
        self.file_path_display.setReadOnly(False)  # Set to True if you want to prevent user editing
        self.file_path_display.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_path_display.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_path_display.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        self.file_path_display.setStyleSheet("background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #404040")
        layout.addWidget(self.file_path_display)

        # Hex color input
        self.hex_color_input = QtWidgets.QLineEdit()
        self.hex_color_input.setFixedSize(430, 30)
        self.hex_color_input.setPlaceholderText("Inserisci il colore esadecimale qui")
        self.hex_color_input.setStyleSheet("background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #404040")
        layout.addWidget(self.hex_color_input)

        # Extract subtitles button
        self.extract_subtitle_button = QtWidgets.QPushButton("Estrai sottotitoli")
        self.extract_subtitle_button.setFixedSize(430, 30)
        self.extract_subtitle_button.clicked.connect(self.extractSubtitles)
        self.extract_subtitle_button.setStyleSheet("background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #404040")
        layout.addWidget(self.extract_subtitle_button)

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
            self.extraction_thread = ExtractSubtitlesThread(self.video_path, self.hex_color_input.text())
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