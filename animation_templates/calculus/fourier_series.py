"""Fourier Series
Shows harmonics accumulating toward a square-wave-like signal.
Keywords: calculus, fourier, harmonics, wave
Difficulty: 4
"""

from manim import Axes, BLUE, LEFT, UP, Create, MathTex, Scene, Text, Write
import numpy as np


class FourierSeriesTemplate(Scene):
    def construct(self):
        axes = Axes(x_range=[-np.pi, np.pi, np.pi / 2], y_range=[-2, 2, 1], x_length=8, y_length=4)
        graph_1 = axes.plot(lambda x: np.sin(x), color=BLUE)
        graph_3 = axes.plot(lambda x: np.sin(x) + np.sin(3 * x) / 3, color="#00FFFF")
        label = MathTex(r"\sin(x) + \frac{1}{3}\sin(3x)").to_edge(UP)
        self.play(Create(axes))
        self.play(Create(graph_1), Write(Text("n = 1").next_to(axes, LEFT)))
        self.play(Create(graph_3), Write(label))
        self.wait(1)
