#!/usr/bin/env python
"""
dent earl, dearl (a) soe ucsc edu
Tool to plot results from checkMap for the Mus Strain Cactus Augustus
project.

Copy-pasta heavily from quick_plot (https://github.com/dentearl/quick_plot/)

example call:

mark_path_1302=~markd/compbio/gencode/mus_strain_cactus/cactusMapCheck/experiments/2014-04-16.simpleChain/results/lnb_0001/chained
mark_path_1405=~markd/compbio/gencode/mus_strain_cactus/cactusMapCheck/experiments/2014-07-17.simpleChain/results/lnb_0001/chained
./delta_coverage_plotter.py --out delta_1302_1405 --ratio --flip $mark_path_1302 $mark_path_1405


"""
##############################
# Copyright (C) 2014 by
# Dent Earl
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
##############################
# plotting boilerplate / cargo cult
import matplotlib
matplotlib.use('Agg')
#####
# the param pdf.fonttype allows for text to be editable in Illustrator.
# Use either Output Type 3 (Type3) or Type 42 (TrueType)
matplotlib.rcParams['pdf.fonttype'] = 42
import matplotlib.backends.backend_pdf as pltBack
import matplotlib.lines as lines
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import matplotlib.pylab as pylab
from matplotlib.ticker import ScalarFormatter, FormatStrFormatter
import numpy
##############################
from argparse import ArgumentParser
from glob import glob
import os
from scipy.stats import scoreatpercentile, linregress, gaussian_kde
import sys
import random

COLOR_MAPS = [m for m in plt.cm.datad if not m.endswith("_r")]


class BadInput(Exception):
  pass


class Row(object):
  """ Class Row holds a single line of a file in split format.
  """
  def __init__(self):
    self.columns = []
    self.line_number = None


class Data(object):
  """ Class Data holds data from one file for plotting.
  """
  def __init__(self):
    self.rows = None  # this will be a list of lists.
    self.names = []  # this will be a list
    self.q_size = []  # this will be a numpy array
    self.bases_mapped = []
    self.fraction_mapped = []
    self.label = ''
  def process_data(self, args):
    i = 1
    for r in self.rows:
      self.names.append(r.columns[0])
      self.q_size.append(int(r.columns[1]))
      self.bases_mapped.append(int(r.columns[2]))
      self.fraction_mapped.append(float(r.columns[3]))
    self.q_size = numpy.array(self.q_size)
    self.bases_mapped = numpy.array(self.bases_mapped)
    self.fraction_mapped = numpy.array(self.fraction_mapped)
    self.categories = {0.0: 0, 0.5: 0, 0.9: 0, 0.95: 0, 0.99:0, 1.0:0}
    for i, row in enumerate(self.rows, 0):
      if self.fraction_mapped[i] == 0:
        self.categories[0.0] += 1
      elif self.fraction_mapped[i] < 0.5:
        self.categories[0.5] += 1
      elif self.fraction_mapped[i] < 0.9:
        self.categories[0.9] += 1
      elif self.fraction_mapped[i] < 0.95:
        self.categories[0.95] += 1
      elif self.fraction_mapped[i] < 1.0:
        self.categories[0.99] += 1
      else:
        self.categories[1.0] += 1

def InitArguments(parser):
  """ Initialize arguments for the program.

  Args:
    parser: an argparse parser object
  """
  parser.add_argument('directories', nargs=2, help='directories to plot')
  parser.add_argument('--out', dest='out', default='my_plot',
                      type=str,
                      help=('path/filename where figure will be created. No '
                            'extension needed. default=%(default)s'))
  parser.add_argument('--ratio', default=False, action='store_true',
                      help='Switch from absolute to ratio.')
  parser.add_argument('--flip', default=False, action='store_true',
                      help='Flip the order of column stacks.')
  parser.add_argument('--total', default='38,329', type=str,
                      help=('total number to display in title. '
                            'default=%(default)s'))
  parser.add_argument('--height', dest='height', default=4.0, type=float,
                      help='height of image, in inches. default=%(default)s')
  parser.add_argument('--width', dest='width', default=9.0, type=float,
                      help='width of image, in inches. default=%(default)s')
  parser.add_argument('--dpi', dest='dpi', default=300,
                      type=int,
                      help=('dots per inch of raster outputs, i.e. '
                            'if --outFormat is all or png. '
                            'default=%(default)s'))
  parser.add_argument('--out_format', dest='out_format', default='pdf',
                      type=str,
                      help=('output format [pdf|png|eps|all]. '
                            'default=%(default)s'))
  parser.add_argument('--ignore_first_n_lines', type=int, default=1,
                      help='Ignore the first n number of lines')


def CheckArguments(args, parser):
  """ Verify that input arguments are correct and sufficient.

  Args:
    args: an argparse arguments object
    parser: an argparse parser object
  """
  args.colors = 'brewer'
  args.color_index_offset = 0
  if len(args.directories) > 0:
    for d in args.directories:
      if not os.path.exists(d):
        parser.error('Directory %s does not exist.\n' % d)
      if not os.path.isdir(d):
        parser.error('Input %s is not a directory.\n' % d)
  else:
    parser.error('File paths must be passed in on command line!')
  if args.dpi < 72:
    parser.error('--dpi %d less than screen res, 72. Must be >= 72.'
                 % args.dpi)
  if args.out_format not in ('pdf', 'png', 'eps', 'all'):
    parser.error('Unrecognized --out_format %s. Choose one from: '
                 'pdf png eps all.' % args.out_format)
  if args.colors not in ('bostock', 'brewer', 'mono'):
    parser.error('Unrecognized --colors %s palette. Choose one from: '
                 'bostock brewer mono.' % args.colors)
  if (args.out.endswith('.png') or args.out.endswith('.pdf') or
      args.out.endswith('.eps')):
    args.out = args.out[:-4]
  args.xmax = -sys.maxint
  args.xmin = sys.maxint
  args.ymax = -sys.maxint
  args.ymin = sys.maxint
  DefineColors(args)


def DefineColors(args):
  """ Based on --colors, define the set of colors to use in the plot.

  Args:
    args: an argparse arguments object
  """
  # TODO: allow for a way to override the color list
  if args.colors == 'bostock':
    args.colors_light = ['#aec7e8',  # l blue
                         '#ffbb78',  # l orange
                         '#98df8a',  # l green
                         '#ff9896',  # l red
                         '#c5b0d5',  # l purple
                         '#c49c94',  # l brown
                         '#f7b6d2',  # l lavender
                         '#c7c7c7',  # l gray
                         '#dbdb8d',  # l olive
                         '#9edae5',  # l aqua
                        ]
    args.colors_medium = ['#1f77b4',  # d blue
                          '#ff7f0e',  # d orange
                          '#2ca02c',  # d green
                          '#d62728',  # d red
                          '#9467bd',  # d purple
                          '#8c564b',  # d brown
                          '#e377c2',  # d lavender
                          '#7f7f7f',  # d gray
                          '#bcbd22',  # d olive
                          '#17becf',  # d aqua
                         ]
    args.colors_dark = []
  elif args.colors == 'brewer':
    args.colors_light = [(136, 189, 230),  # l blue
                         (251, 178,  88),  # l orange
                         (144, 205, 151),  # l green
                         (246, 170, 201),  # l red
                         (191, 165,  84),  # l brown
                         (188, 153, 199),  # l purple
                         (240, 126, 110),  # l magenta
                         (140, 140, 140),  # l grey
                         (237, 221,  70),  # l yellow
                        ]
    args.colors_medium = [( 93, 165, 218),  # m blue
                          (250, 164,  58),  # m orange
                          ( 96, 189, 104),  # m green
                          (241, 124, 167),  # m red
                          (178, 145,  47),  # m brown
                          (178, 118, 178),  # m purple
                          (241,  88,  84),  # m magenta
                          ( 77,  77,  77),  # m grey
                          (222, 207,  63),  # m yellow
                         ]
    args.colors_dark = [( 38,  93, 171),  # d blue
                        (223,  92,  36),  # d orange
                        (  5, 151,  72),  # d green
                        (229,  18, 111),  # d red
                        (157, 114,  42),  # d brown
                        (123,  58, 150),  # d purple
                        (203,  32,  39),  # d magenta
                        (  0,   0,   0),  # black
                        (199, 180,  46),  # d yellow
                       ]
  elif args.colors == 'mono':
    args.colors_light = [(140, 140, 140),  # l grey
                        ]
    args.colors_medium = [( 77,  77,  77),  # m grey
                         ]
    args.colors_dark = [(  0,   0,   0),  # black
                       ]
  elif args.colors == 'hcl_ggplot2':
    args.colors_light = [(158, 217, 255),  # l blue
                         (246, 209, 146),  # l mustard
                         ( 93, 237, 189),  # l green
                         (255, 189, 187),  # l pink
                         (182, 228, 149),  # l olive
                         ( 51, 235, 236),  # l teal
                         (241, 194, 255),  # l purple
                         (255, 179, 234),  # l magenta
                        ]
    args.colors_medium = [( 98, 162, 209),  # m blue
                          (190, 154,  87),  # m mustard
                          (223, 133, 131),  # m pink
                          (  0, 183, 134),  # m green
                          (126, 173,  90),  # m olive
                          (  0, 180, 181),  # m teal
                          (187, 134, 209),  # m purple
                          (225, 122, 179),  # m magenta
                         ]
    args.colors_dark = [(  0, 163, 255),  # d blue
                        (213, 151,   0),  # d mustard
                        (  0, 201, 106),  # d green
                        (254, 102,  97),  # d pink
                        ( 98, 183,   0),  # d olive
                        (  1, 196, 200),  # d teal
                        (219,  95, 255),  # d purple
                        (255,  40, 201),  # d magenta
                       ]
  if isinstance(args.colors_light[0], tuple):
    CorrectColorTuples(args)


def CorrectColorTuples(args):
  """ Corrects the 0-255 values in colors_light and colors_medium to 0.0 - 1.0.

  Args:
    args: an argparse arguments object
  """
  for i in xrange(0, len(args.colors_light)):
    args.colors_light[i] = (args.colors_light[i][0] / 255.0,
                            args.colors_light[i][1] / 255.0,
                            args.colors_light[i][2] / 255.0,)
  for i in xrange(0, len(args.colors_medium)):
    args.colors_medium[i] = (args.colors_medium[i][0] / 255.0,
                             args.colors_medium[i][1] / 255.0,
                             args.colors_medium[i][2] / 255.0,)
  for i in xrange(0, len(args.colors_dark)):
    args.colors_dark[i] = (args.colors_dark[i][0] / 255.0,
                           args.colors_dark[i][1] / 255.0,
                           args.colors_dark[i][2] / 255.0,)


def InitImage(args):
  """ Initialize a new image.

  Args:
    args: an argparse arguments object

  Returns:
    fig: a matplotlib figure object
    pdf: a matplotlib pdf drawing (backend) object
  """
  pdf = None
  if args.out_format == 'pdf' or args.out_format == 'all':
    pdf = pltBack.PdfPages(args.out + '.pdf')
  fig = plt.figure(figsize=(args.width, args.height),
                   dpi=args.dpi, facecolor='w')
  return (fig, pdf)


def EstablishAxes(fig, args):
  """ Create a single axis on the figure object.

  Args:
    fig: a matplotlib figure object
    args: an argparse arguments object

  Returns:
    ax: a matplotlib axis object
  Raises:
    ValueError: If an unknown spine location is passed.
  """
  # left 0.99 inches, right 0.54 inches, width 7.47 inches
  # bottom 0.68 inches, top 0.28 inches, height 3.04 inches
  args.axLeft = 1.1 / args.width
  args.axRight = 1.0 - (1.3 / args.width)
  args.axWidth = args.axRight - args.axLeft
  args.axBottom = 0.9 / args.height
  args.axTop = 1.0 - (0.4 / args.height)
  args.axHeight = args.axTop - args.axBottom
  ax = fig.add_axes([args.axLeft, args.axBottom,
                     args.axWidth, args.axHeight])
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


def WriteImage(fig, pdf, args):
  """ Write the image to disk.

  Args:
    fig: a matplotlib figure object
    pdf: a matplotlib pdf drawing (backend) object
    args: an argparse arguments object
  """
  if args.out_format == 'pdf':
    fig.savefig(pdf, format = 'pdf')
    pdf.close()
  elif args.out_format == 'png':
    fig.savefig(args.out + '.png', format='png', dpi=args.dpi)
  elif args.out_format == 'all':
    fig.savefig(pdf, format='pdf')
    pdf.close()
    fig.savefig(args.out + '.png', format='png', dpi=args.dpi)
    fig.savefig(args.out + '.eps', format='eps')
  elif args.out_format == 'eps':
    fig.savefig(args.out + '.eps', format='eps')


def ReadDirs(args):
  """ Read all *basestats files from each directory, return list of deltas.

  Args:
    args: an argparse arguments object

  Returns:
    deltas: a list of Data() objects
  """
  deltas = []
  stats = {}
  files = glob(os.path.join(args.directories[0], '*basestats'))
  for a_file in files:
    d = FileToData(a_file, args)
    stats[d.label] = d
  files = glob(os.path.join(args.directories[1], '*basestats'))
  for a_file in files:
    d = FileToData(a_file, args)
    if d.label not in stats:
      # we can't get deltas on things not in the original run.
      continue
    deltas.append(CreateDelta(stats[d.label], d, args))
  return deltas


def CreateDelta(d1, d2, args):
  """ given two data objects, create the delta d2 - d1.
  """
  delta = Data()
  assert(d1.label == d2.label)
  delta.label = d1.label
  delta.categories = {0.0: 0, 0.5: 0, 0.9: 0, 0.95: 0, 0.99:0, 1.0:0}
  delta.d2_categories = {0.0: 0, 0.5: 0, 0.9: 0, 0.95: 0, 0.99:0, 1.0:0}
  if args.ratio:
    # normalize the data to 1.0
    for d in [d1, d2]:
      norm = 0.0
      for key in [0.0, 0.5, 0.9, 0.95, 0.99, 1.0]:
        norm += d.categories[key]
      if norm == 0:
        print d.label
        print d.categories
      assert(norm != 0)
      for key in [0.0, 0.5, 0.9, 0.95, 0.99, 1.0]:
        d.categories[key] /= float(norm)
  # for sorting:
  delta.fraction_mapped = d2.fraction_mapped
  for key in delta.categories:
    delta.categories[key] = d2.categories[key] - d1.categories[key]
    delta.d2_categories[key] = d2.categories[key]
  return delta


def FileToData(a_file, args):
  """ Read A_FILE and return a Data object.
  """
  num_columns = None
  f = open(a_file, 'r')
  rows = []
  line_number = 0
  for line in f:
    line_number += 1
    line = line.strip()
    if line.startswith('#'):
      continue
    if line_number <= args.ignore_first_n_lines:
      continue
    r = Row()
    r.columns = line.split()
    r.line_number = line_number
    rows.append(r)
  f.close()
  d = Data()
  d.label = os.path.basename(a_file)
  d.rows = rows
  d.process_data(args)
  return d


def ColorPicker(i, args):
  """ Returns a valid matplotlib color based on the index, plot mode & palette.

  Args:
    i: index, integer
    args: an argparse arguments object

  Returns:
    color: a valid matplotlib color, or a list of colors if mode is hist
           or a name of a valid matplotlib colormap or a matplotlib color map
           if the mode is contour
  """
  i += args.color_index_offset
  return args.colors_light[i % len(args.colors_light)]


def PlotBars(ax, data_list, stacks, width, args):
  """ Plot all of the bars on the axis.
  """
  order = [0.0, 0.5, 0.9, 0.95, 0.99, 1.0]
  bars = []
  if args.flip:
    order.reverse()
  offset = 0
  for i, key in enumerate(order, 0):
    bars.append(ax.bar([x + offset for x in range(0, len(data_list))],
                       stacks[key],
                       width,
                       color=ColorPicker(i, args), linewidth=0.0, alpha=1.0))
    offset += width
  return bars


def PlotDeltas(data_list, ax, args):
  """ Plot deltas!

  Args:
    data_list: a list of Data objects.
    ax: a matplotlib axis object.
    args: an argparse argument object.
  """
  # 88,093
  ylabel = 'Delta Number of transcripts'
  args.title = ('Change in count of %s transcipts from mm10 (C57B6J) '
                'mapped to other strains / species' % args.total)
  width = 0.133  # 0.8 / 6
  data_min = -0.2
  data_max = 1.0
  args.xmin = 0
  args.xmax = len(data_list)
  lines.Line2D([0.0, len(data_list)], [0.0, 0.0], color='gray')
  if args.ratio:
    # normalize the data to 1.0
    ylabel = 'Change in Proportion of transcripts'
    args.title = ('Change in Fraction of %s transcipts from mm10 (C57B6J)  '
                  'mapped to other strains / species ' % args.total)
  data_order = []
  # sort data according to 1.0 level of the d2 data, not the delta data
  data_order = sorted(data_list, key=lambda d: d.d2_categories[1.0],
                      reverse=True)
  labels = [d.label.split('.')[0] for d in data_order]
  deltas = {0.0: [], 0.5: [], 0.9: [], 0.95: [], 0.99:[], 1.0:[]}
  for data in data_order:
    for v in [0.0, 0.5, 0.9, 0.95, 0.99, 1.0]:
      deltas[v].append(data.categories[v])
  for v in [0.0, 0.5, 0.9, 0.95, 0.99, 1.0]:
    deltas[v] = numpy.array(deltas[v])
  # plot stacked bar chart
  bars = PlotBars(ax, data_list, deltas, width, args)

  legend_labels = ['1.0', '< 1.0', '< 0.95', '< 0.9', '< 0.5', '0']
  if args.flip:
    legend_labels.reverse()
  leg = ax.legend([bars[5][0], bars[4][0], bars[3][0],
                   bars[2][0], bars[1][0], bars[0][0]],
                  legend_labels,
                  bbox_to_anchor=(0,-0.1,1,1),  # place legend outside of axis
                  bbox_transform=plt.gcf().transFigure)
  leg.get_frame().set_edgecolor('white')
  xmin, xmax, ymin, ymax = ax.axis()
  ax.xaxis.set_ticks(numpy.arange(0, len(data_list)) + width/2.0)
  ax.xaxis.set_ticklabels(labels, rotation=45)
  ax.set_ylabel(ylabel)
  ax.yaxis.set_ticks(numpy.arange(-10.0,10.0)/100)
  ax.yaxis.set_ticklabels([str(x) + "%" for x in range(-10,10)])
  # raise the title up a bit
  plt.text(0.5, 1.08, args.title,
         horizontalalignment='center',
         fontsize=12,
         transform=ax.transAxes)


def PlotData(data_list, ax, args):
  """ Plot all of the data according to input arguments.

  Args:
    data_list: a list of Data objects.
    ax: a matplotlib axis object.
    args: an argparse argument object.
  """
  PlotDeltas(data_list, ax, args)


def main():
  usage = '%(prog)s dir1 dir2 [options]\n\n'
  parser = ArgumentParser(usage=usage)
  InitArguments(parser)
  args = parser.parse_args()
  CheckArguments(args, parser)
  fig, pdf = InitImage(args)
  ax = EstablishAxes(fig, args)

  data_list = ReadDirs(args)
  PlotData(data_list, ax, args)

  WriteImage(fig, pdf, args)


if __name__ == '__main__':
    main()
