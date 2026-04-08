"""Pythagorean Theorem
Visual proof of a right triangle with squares built on each side.
Keywords: geometry, triangle, proof, squares, pythagorean
Difficulty: 2
"""

from manim import BLUE, DOWN, GREEN, LEFT, RED, RIGHT, UP, Create, FadeIn, Polygon, Scene, Square, Text, VGroup, Write


class PythagoreanTemplate(Scene):
    def construct(self):
        triangle = Polygon((-3, -1.5, 0), (1, -1.5, 0), (-3, 1.5, 0), color=BLUE)
        label = Text("a^2 + b^2 = c^2").to_edge(UP)
        square_a = Square(side_length=2, color=GREEN).next_to(triangle, LEFT, buff=0.2)
        square_b = Square(side_length=3, color=RED).next_to(triangle, DOWN, buff=0.2)
        square_c = Square(side_length=3.6, color=BLUE).rotate(-0.93).next_to(triangle, RIGHT, buff=0.2)
        self.play(Create(triangle))
        self.play(FadeIn(VGroup(square_a, square_b, square_c)))
        self.play(Write(label))
        self.wait(1)
