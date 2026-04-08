"""Binary Search
Shows left, mid, and right pointers shrinking the search interval.
Keywords: binary search, pointers, algorithm, array, cs
Difficulty: 2
"""

from manim import BLUE, GREEN, ORANGE, RED, RIGHT, UP, FadeToColor, Rectangle, Scene, Text, VGroup, Write, Create


class BinarySearchTemplate(Scene):
    def construct(self):
        cells = VGroup(*[Rectangle(width=0.9, height=0.9, color=BLUE) for _ in range(7)]).arrange(RIGHT, buff=0.15)
        labels = VGroup(*[Text(str(value), font_size=24).move_to(cell.get_center()) for value, cell in zip([1, 3, 5, 7, 9, 11, 13], cells)])
        title = Text("Binary Search").to_edge(UP)
        self.play(Write(title), Create(cells), Write(labels))
        self.play(FadeToColor(cells[3], ORANGE))
        self.play(FadeToColor(VGroup(cells[0], cells[1], cells[2]), RED))
        self.play(FadeToColor(cells[5], ORANGE), FadeToColor(cells[4], GREEN))
        self.wait(1)
