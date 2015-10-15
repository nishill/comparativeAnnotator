"""
This file contains convenience functions for plotting.
"""
import os
import itertools
import math
import numpy as np
from collections import defaultdict, OrderedDict

import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['pdf.fonttype'] = 42
import matplotlib.lines as lines
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.pylab as pylab
import matplotlib.backends.backend_pdf as plt_back
from etc.config import *

__author__ = "Ian Fiddes"


def init_image(out_folder, comparison_name, width, height):
    """
    Sets up a PDF object.
    """
    pdf = plt_back.PdfPages(os.path.join(out_folder, comparison_name + ".pdf"))
    # width by height in inches
    fig = plt.figure(figsize=(width, height), dpi=300, facecolor='w')
    return fig, pdf


def establish_axes(fig, width, height, border=True, has_legend=True):
    """
    Sets up custom axes. The extra space given is adjusted by border and has_legend.
    """
    ax_left = 1.1 / width
    if border is True:
        if has_legend is True:
            ax_right = 1.0 - (1.8 / width)
        else:
            ax_right = 1.0 - (1.15 / width)
    else:
        if has_legend is True:
            ax_right = 1.1 - (1.8 / width)
        else:
            ax_right = 1.1 - (1.15 / width)
    ax_width = ax_right - ax_left
    ax_bottom = 1.4 / height
    ax_top = 0.90 - (0.4 / height)
    ax_height = ax_top - ax_bottom
    ax = fig.add_axes([ax_left, ax_bottom, ax_width, ax_height])
    ax.yaxis.set_major_locator(pylab.NullLocator())
    ax.xaxis.set_major_locator(pylab.NullLocator())
    for loc, spine in ax.spines.iteritems():
        if loc in ['left', 'bottom']:
            spine.set_position(('outward', 10))
        elif loc in ['right', 'top']:
            spine.set_color('none')
        else:
            raise ValueError('unknown spine location: %s' % loc)
    ax.xaxis.set_ticks_position('bottom')
    ax.yaxis.set_ticks_position('left')
    return ax


def adjust_x_labels(ax, names, cutoff1=12, cutoff2=18, cutoff3=26):
    """
    If your xaxis labels have a variable amount of text, this can adjust them individually
    """
    for n, t in itertools.izip(*[names, ax.xaxis.get_major_ticks()]):
        if cutoff2 > len(n) > cutoff1:
            t.label1.set_fontsize(8)
        elif cutoff3 > len(n) >= cutoff2:
            t.label1.set_fontsize(7)
        elif len(n) >= cutoff2:
            t.label1.set_fontsize(6)


def base_barplot(max_y_value, names, out_path, file_name, title_string, border=True, has_legend=True):
    """
    Used to initialize either a stacked or unstacked barplot. Expects the max y value to be somewhere in the 10-100
    range or things will get weird.
    """
    assert 10 <= max_y_value <= 100, (max_y_value, names, out_path, file_name, title_string)
    fig, pdf = init_image(out_path, file_name, width, height)
    ax = establish_axes(fig, width, height, border, has_legend)
    plt.text(0.5, 1.08, title_string, horizontalalignment='center', fontsize=12, transform=ax.transAxes)
    ax.set_ylabel("Proportion of transcripts")
    ax.set_ylim([0, max_y_value])
    plt.tick_params(axis='y', labelsize=9)
    plt.tick_params(axis='x', labelsize=9)
    ax.yaxis.set_ticks(np.arange(0.0, int(max_y_value + 1), max_y_value / 10))
    ax.yaxis.set_ticklabels([str(x) + "%" for x in range(0, int(max_y_value + 1), int(max_y_value / 10))])
    ax.xaxis.set_ticks(np.arange(0, len(names)) + bar_width / 2.0)
    ax.xaxis.set_ticklabels(names, rotation=60)
    return ax, fig, pdf


def barplot(results, out_path, file_name, title_string, color="#0072b2", border=True, add_labels=True, adjust_y=True):
    """
    Boilerplate code that will produce a unstacked barplot. Expects results to be a list of lists in the form
    [[name1, value1], [name2, value2]]. The values should be normalized between 0 and 100.
    """
    names, values, raw_values = zip(*results)
    if adjust_y is True:
        max_y_value = math.ceil(max(values) / 10.0) * 10
    else:
        max_y_value = 100.0
    ax, fig, pdf = base_barplot(max_y_value, names, out_path, file_name, title_string, border=border, has_legend=False)
    bars = ax.bar(range(len(names)), values, bar_width, color=color)
    if add_labels is True:
        for i, rect in enumerate(bars):
            v = "{:,}".format(raw_values[i])
            ax.text(rect.get_x() + bar_width / 2.0, 0.0 + rect.get_height(), v, ha='center', va='bottom', size=6)
    if max(len(x) for x in names) > 15:
        adjust_x_labels(ax, names)
    fig.savefig(pdf, format='pdf')
    plt.close()
    pdf.close()


def stacked_barplot(results, legend_labels, out_path, file_name, title_string, color_palette=palette, border=True):
    """
    Boilerplate code that will produce a unstacked barplot. Expects results to be a list of lists of lists in the form
    [[name1, value1], [name2, value2]]. The values should be normalized between 0 and 100. Should be in the same
    order as legend_labels or your legend will be wrong.
    """
    names, values = zip(*results)
    ax, fig, pdf = base_barplot(100.0, names, out_path, file_name, title_string, border=border, has_legend=True)
    bars = []
    cumulative = np.zeros(len(values))
    for i, d in enumerate(np.asarray(values).transpose()):
        bars.append(ax.bar(range(len(values)), d, bar_width, bottom=cumulative,
                           color=color_palette[i % len(color_palette)],
                           linewidth=0.0, alpha=1.0))
        cumulative += d
    fig.legend([x[0] for x in bars[::-1]], legend_labels[::-1], bbox_to_anchor=(1, 0.8), fontsize=11,
               frameon=True, title="Category")
    fig.savefig(pdf, format='pdf')
    plt.close()
    pdf.close()