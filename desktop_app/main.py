import sys

from PySide6.QtWidgets import QApplication

from widgets.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(
        """
        QWidget { font-family: Segoe UI, Arial; font-size: 13px; }
        QLineEdit, QComboBox, QTextEdit, QDateEdit, QTimeEdit {
            padding: 6px;
            border: 1px solid #b8c4bd;
            border-radius: 4px;
        }
        QPushButton {
            padding: 7px 12px;
            border: 1px solid #597267;
            border-radius: 4px;
            background: #eef5f1;
        }
        QPushButton:hover { background: #dfece6; }
        QTableWidget { gridline-color: #d6ded9; selection-background-color: #cfe3d8; }
        """
    )
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
