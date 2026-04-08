"""Unit Circle Sine And Cosine
Tracks a rotating point and the corresponding sine / cosine values.
Keywords: trigonometry, unit circle, sine, cosine
Difficulty: 3
"""

from manim import Circle, Dot, Line, Scene, Text, UP, ValueTracker, always_redraw, Create, Write
import numpy as np


class UnitCircleTemplate(Scene):
    def construct(self):
        circle = Circle(radius=2)
        angle = ValueTracker(0)
        dot = always_redraw(lambda: Dot((2 * np.cos(angle.get_value()), 2 * np.sin(angle.get_value()), 0), color="#FFD700"))
        radius = always_redraw(lambda: Line((0, 0, 0), dot.get_center(), color="#00FFFF"))
        title = Text("Unit Circle").to_edge(UP)
        self.play(Write(title), Create(circle))
        self.play(Create(radius), Create(dot))
        self.play(angle.animate.set_value(np.pi / 2))
        self.play(angle.animate.set_value(np.pi))
        self.wait(1)
