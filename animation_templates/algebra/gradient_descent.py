"""Gradient Descent
A point steps downhill on a parabola while the update rule is displayed.
Keywords: optimization, gradient descent, parabola, algebra
Difficulty: 3
"""

from manim import Axes, Dot, MathTex, RED, UP, Scene, Create, Write


class GradientDescentTemplate(Scene):
    def construct(self):
        axes = Axes(x_range=[-4, 4, 1], y_range=[0, 9, 2], x_length=7, y_length=4)
        curve = axes.plot(lambda x: 0.5 * x * x + 1, color=RED)
        point = Dot(axes.c2p(3, 5.5), color="#00FFFF")
        rule = MathTex(r"x_{t+1}=x_t-\eta \nabla f(x_t)").to_edge(UP)
        self.play(Create(axes), Create(curve))
        self.play(Write(rule), Create(point))
        self.play(point.animate.move_to(axes.c2p(1.5, 2.1)))
        self.play(point.animate.move_to(axes.c2p(0.5, 1.1)))
        self.wait(1)
