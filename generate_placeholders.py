import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient
from PyQt6.QtCore import Qt, QRect


def generate_placeholder(filename, text, subtitle):
    # Initialize QApplication to allow QPixmap usage
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    width, height = 400, 300
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw gradient background
    gradient = QLinearGradient(0, 0, width, height)
    gradient.setColorAt(0, QColor("#1e1e3f"))
    gradient.setColorAt(1, QColor("#0d0d1a"))
    painter.fillRect(QRect(0, 0, width, height), gradient)

    # Draw soft rim
    painter.setPen(QColor("#3f3f6f"))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(1, 1, width-2, height-2, 8, 8)

    # Draw text
    painter.setPen(QColor("#c77dff"))
    font = QFont("Microsoft YaHei UI", 24, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRect(0, height//2 - 40, width, 40), Qt.AlignmentFlag.AlignCenter, text)

    painter.setPen(QColor("#8888aa"))
    font2 = QFont("Microsoft YaHei UI", 14)
    painter.setFont(font2)
    painter.drawText(QRect(0, height//2 + 10, width, 40), Qt.AlignmentFlag.AlignCenter, subtitle)

    painter.end()
    pixmap.save(filename, "PNG")


def main():
    import os
    os.makedirs('res/img', exist_ok=True)
    generate_placeholder("res/img/cat_play.png", "A Cat Playing", "Visual Scene Placeholder")
    generate_placeholder("res/img/cat_garden.png", "Running in Garden", "Visual Scene Placeholder")

    generate_placeholder("res/img/mountain_sunny.png", "A Sunny Day", "Visual Scene Placeholder")
    generate_placeholder("res/img/mountain_climb.png", "Climbing the Mountain", "Visual Scene Placeholder")
    generate_placeholder("res/img/mountain_trees.png", "Trees on the Mountain", "Visual Scene Placeholder")
    generate_placeholder("res/img/mountain_happy.png", "Very Happy", "Visual Scene Placeholder")

    generate_placeholder("res/img/friend_1.png", "Good Friend", "Visual Scene Placeholder")
    generate_placeholder("res/img/friend_2.png", "Going to School", "Visual Scene Placeholder")
    generate_placeholder("res/img/friend_3.png", "Eating Apples", "Visual Scene Placeholder")

    generate_placeholder("res/img/morning_1.png", "Sun Came Out", "Visual Scene Placeholder")
    generate_placeholder("res/img/morning_2.png", "Drinking Water", "Visual Scene Placeholder")
    generate_placeholder("res/img/morning_3.png", "Feeling Happy", "Visual Scene Placeholder")


if __name__ == "__main__":
    main()
