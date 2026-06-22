import matplotlib.pyplot as plt
import numpy as np
from typing import Dict

def render_radar_chart(
    traits: Dict[str, float],
    color: str = '#3b82f6',
    bg_color: str = '#0f172a',
    title: str = "",
    figsize: tuple = (4, 4)
) -> plt.Figure:
    """
    Renders a dynamic radar chart for any number of axes.
    traits: Dictionary mapping label names to their float values (0.0 to 1.0).
    """
    labels = list(traits.keys())
    values = list(traits.values())
    
    num_vars = len(labels)
    # Compute angles for chart
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    
    # Complete the loop
    values += values[:1]
    angles += angles[:1]
    
    # Create plot
    fig, ax = plt.subplots(figsize=figsize, subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)
    
    # Draw logic
    ax.plot(angles, values, color=color, linewidth=2)
    
    # Handle alpha from hex color string if possible, or just use 0.35
    ax.fill(angles, values, color=color[:7], alpha=0.35)
    
    # Correct orientation
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    
    # Add axis labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, color='white', size=8)
    
    # Y Labels
    ax.set_rlabel_position(0)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels([], color="grey", size=7) 
    ax.set_ylim(0, 1)
    
    if title:
        ax.set_title(title, color='white', size=10, pad=15)
    
    # Sub-styles
    ax.spines['polar'].set_color(bg_color)
    ax.grid(color='grey', linestyle='--', alpha=0.2)

    return fig
