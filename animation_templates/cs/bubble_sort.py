"""Bubble Sort
Animated comparison and swap process for a short array of bars.
Keywords: sorting, bubble sort, cs, algorithm, bars
Difficulty: 2
"""

from manim import BLUE, GREEN, ORANGE, RIGHT, UP, Create, FadeToColor, Rectangle, Scene, Text, VGroup, Write


class BubbleSortTemplate(Scene):
    def construct(self):
        values = [2, 4, 1, 5, 3]
        bars = VGroup(*[Rectangle(height=value, width=0.6, color=BLUE) for value in values]).arrange(RIGHT, buff=0.25).move_to((0, -1, 0))
        title = Text("Bubble Sort").to_edge(UP)
        self.play(Write(title), Create(bars))
        self.play(FadeToColor(bars[1], ORANGE), FadeToColor(bars[2], ORANGE))
        self.play(bars[1].animate.move_to(bars[2].get_center()), bars[2].animate.move_to(bars[1].get_center()))
        self.play(FadeToColor(bars, GREEN))
        self.wait(1)
