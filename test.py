from manim import Scene, Axes, FunctionGraph, Dot, WHITE, GRAY_A, Create, FadeIn, FadeOut, Arrow, MathTex, UP, DOWN, VGroup, Transform, TexTemplate
import numpy as np

class GradientDescentParabola(Scene):
    def construct(self):
        # --- Configuration ---
        learning_rate = 0.1
        num_steps = 10
        initial_x = -2.5
        x_range = [-3, 3, 1]
        y_range = [0, 9, 1] # For x^2, max y is 3^2 = 9
        arrow_length_factor = 0.3 # Controls the visual length of the gradient arrow

        # --- Visual Style ---
        self.camera.background_color = "#000000" # Pure black background

        # --- Functions ---
        def f(x):
            return x**2

        def f_prime(x):
            return 2 * x

        # --- Setup Axes ---
        axes = Axes(
            x_range=x_range,
            y_range=y_range,
            x_length=6,
            y_length=6,
            axis_config={"color": GRAY_A, "include_numbers": False, "include_ticks": False},
        )
        # Add numbers to axes and set their color to muted gray
        axes.add_coordinates()
        axes.x_axis.numbers.set_color(GRAY_A)
        axes.y_axis.numbers.set_color(GRAY_A)

        labels = axes.get_axis_labels(x_label="x", y_label="f(x)")
        labels.set_color(GRAY_A)

        self.play(Create(axes), Create(labels), run_time=1.5)
        self.wait(1)

        # --- Plot Parabola ---
        parabola = axes.plot(f, color=WHITE)
        self.play(Create(parabola), run_time=2)
        self.wait(1)

        # --- Gradient Descent Update Rule ---
        # FIX: Initialize TexTemplate directly with the desired documentclass in the constructor.
        # This ensures 'standalone.cls' is not requested if it's missing, as the default
        # documentclass for TexTemplate is 'standalone' if not specified.
        custom_tex_template = TexTemplate(documentclass=r"\documentclass[preview]{article}")

        update_rule = MathTex(
            r"x_{n+1} = x_n - \alpha \nabla f(x_n)",
            color=WHITE,
            tex_template=custom_tex_template # Apply custom template
        ).to_edge(UP).shift(DOWN * 0.5)
        self.play(Write(update_rule), run_time=2)
        self.wait(1)

        # --- Initial Dot ---
        current_x = initial_x
        dot = Dot(axes.coords_to_point(current_x, f(current_x)), color=WHITE)
        self.play(FadeIn(dot), run_time=1)
        self.wait(1)

        # --- Gradient Descent Steps ---
        # Placeholder for the step number text, initialized as empty
        current_step_text = MathTex("", color=WHITE, tex_template=custom_tex_template).next_to(update_rule, DOWN, buff=0.5)
        self.add(current_step_text) # Add it to the scene so it can be transformed

        for i in range(num_steps):
            # Calculate gradient and next x
            gradient = f_prime(current_x)
            next_x = current_x - learning_rate * gradient

            # Create gradient arrow
            arrow_start_point = axes.coords_to_point(current_x, f(current_x))
            
            # The arrow represents the direction of the negative gradient in the x-dimension.
            # Its length is proportional to the step size, scaled by arrow_length_factor.
            arrow_end_x_coord = current_x - arrow_length_factor * learning_rate * gradient
            # The y-coordinate remains the same for a horizontal arrow, representing the x-component of the gradient.
            arrow_end_point = axes.coords_to_point(arrow_end_x_coord, f(current_x)) 

            gradient_arrow = Arrow(
                start=arrow_start_point,
                end=arrow_end_point,
                buff=0,
                color=WHITE,
                stroke_width=4,
                max_stroke_width_to_length_ratio=10, # Ensures tip is visible for short arrows
                max_tip_length_to_total_length_ratio=0.3
            )
            
            # Update step number text
            new_step_text = MathTex(f"\\text{{Step }} {i+1}", color=WHITE, tex_template=custom_tex_template).next_to(update_rule, DOWN, buff=0.5)
            self.play(Transform(current_step_text, new_step_text), run_time=1)
            self.wait(0.5) # Shorter wait for text update

            self.play(Create(gradient_arrow), run_time=1.5)
            self.wait(1)

            # Animate dot movement along the curve
            self.play(
                dot.animate.move_to(axes.coords_to_point(next_x, f(next_x))),
                run_time=2,
                rate_func=lambda t: t # Linear movement
            )
            self.wait(1)

            self.play(FadeOut(gradient_arrow), run_time=1)
            current_x = next_x

        self.wait(2)
        # Fade out all remaining objects
        self.play(FadeOut(VGroup(axes, labels, parabola, update_rule, dot, current_step_text)))
        self.wait(1)