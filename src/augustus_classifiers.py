import re
from collections import defaultdict, Counter
import lib.seq_lib as seq_lib
import lib.psl_lib as psl_lib
import lib.comp_ann_lib as comp_ann_lib
from src.abstract_classifier import AbstractAugustusClassifier


class NotSameStrand(AbstractAugustusClassifier):
    """
    Does this transcript exist on the same strand?
    """
    @property
    def rgb(self):
        return self.colors["generic"]

    def run(self):
        for aug_aln_id, aug_t, t in self.augustus_transcript_transmap_iterator():
            if aug_t.strand != t.strand:
                self.classify_dict[aug_aln_id] = 1
                bed_rec = seq_lib.transcript_to_bed(aug_t, self.rgb, self.column)
                self.details_dict[aug_aln_id].append(bed_rec)
            else:
                self.classify_dict[aug_aln_id] = 0
        self.dump_results_to_disk()


class MultipleTranscripts(AbstractAugustusClassifier):
    """
    Does this transcript appear more than once in the augustus transcript dict?
    """
    @property
    def rgb(self):
        return self.colors["generic"]

    def run(self):
        r = re.compile("-[0-9]+-")
        self.get_augustus_transcript_dict()
        counts = Counter("-".join(r.split(aug_aln_id)) for aug_aln_id in self.augustus_transcript_dict)
        for aug_aln_id, aug_t in self.augustus_transcript_iterator():
            aug_base_id = "-".join(r.split(aug_aln_id))
            if counts[aug_base_id] > 1:
                n = self.column + "_{}_Copies".format(counts[aug_base_id] - 1)
                bed_rec = seq_lib.transcript_to_bed(aug_t, self.rgb, n)
                self.details_dict[aug_aln_id].append(bed_rec)
                self.classify_dict[aug_aln_id] = 1
            else:
                self.classify_dict[aug_aln_id] = 0
        self.dump_results_to_disk()


class ExonGain(AbstractAugustusClassifier):
    """
    Does the augustus version of this transcript add an exon?
    This is calculated by looking at the exon boundary intervals between the genePreds
    we expect new exons to not be within the gap-merged exons of the transMap genes.
    """
    @property
    def rgb(self):
        return self.colors["generic"]

    def run(self):
        for aug_aln_id, aug_t, t in self.augustus_transcript_transmap_iterator():
            aug_t_intervals = aug_t.exon_intervals
            merged_t_intervals = seq_lib.gap_merge_intervals(t.exon_intervals, gap=comp_ann_lib.short_intron_size)
            for interval in aug_t_intervals:
                if seq_lib.interval_not_intersect_intervals(merged_t_intervals, interval):
                    bed_rec = interval.get_bed(self.rgb, "/".join([self.column, aug_aln_id]))
                    self.details_dict[aug_aln_id].append(bed_rec)
            if len(self.details_dict[aug_aln_id]) > 0:
                self.classify_dict[aug_aln_id] = 1
            else:
                self.classify_dict[aug_aln_id] = 0
        self.dump_results_to_disk()


class ExonLoss(AbstractAugustusClassifier):
    """
    Does the augustus version of this transcript lose an exon?
    This is calculated by looking at the exon boundary intervals between the genePreds
    """
    @property
    def rgb(self):
        return self.colors["generic"]

    def run(self, short_intron_size=30):
        for aug_aln_id, aug_t, t in self.augustus_transcript_transmap_iterator():
            aug_t_intervals = aug_t.exon_intervals
            merged_t_intervals = seq_lib.gap_merge_intervals(t.exon_intervals, gap=comp_ann_lib.short_intron_size)
            for interval in merged_t_intervals:
                if seq_lib.interval_not_intersect_intervals(aug_t_intervals, interval):
                    bed_rec = interval.get_bed(self.rgb, "/".join([self.column, aug_aln_id]))
                    self.details_dict[aug_aln_id].append(bed_rec)
            if len(self.details_dict[aug_aln_id]) > 0:
                self.classify_dict[aug_aln_id] = 1
            else:
                self.classify_dict[aug_aln_id] = 0
        self.dump_results_to_disk()


class NotSimilarInternalExonBoundaries(AbstractAugustusClassifier):
    """
    Does the augustus version of this transcript have the same exon boundaries, within a wiggle room range?
    Returns True if any internal exons are NOT in the same boundaries, and also reports each such splice junction
    """
    @property
    def rgb(self):
        return self.colors["generic"]

    def run(self, short_intron_size=50, wiggle_room=30):
        for aug_aln_id, aug_t, t in self.augustus_transcript_transmap_iterator():
            merged_t_intervals = seq_lib.gap_merge_intervals(t.exon_intervals, gap=short_intron_size)
            merged_t_intervals = merged_t_intervals[1:-1]
            aug_t_intervals = aug_t.exon_intervals[1:-1]
            for interval in merged_t_intervals:
                if seq_lib.interval_not_within_wiggle_room_intervals(aug_t_intervals, interval, wiggle_room):
                    bed_rec = interval.get_bed(self.rgb, "/".join([self.column, aug_aln_id]))
                    self.details_dict[aug_aln_id].append(bed_rec)
            if len(self.details_dict[aug_aln_id]) > 0:
                self.classify_dict[aug_aln_id] = 1
            else:
                self.classify_dict[aug_aln_id] = 0
        self.dump_results_to_disk()


class NotSimilarTerminalExonBoundaries(AbstractAugustusClassifier):
    """
    Does the augustus version of this transcript have the same terminal exon boundaries?
    """
    @property
    def rgb(self):
        return self.colors["generic"]

    def run(self, short_intron_size=100, wiggle_room=200):
        for aug_aln_id, aug_t, t in self.augustus_transcript_transmap_iterator():
            merged_t_intervals = seq_lib.gap_merge_intervals(t.exon_intervals, gap=short_intron_size)
            merged_t_intervals = [merged_t_intervals[0], merged_t_intervals[-1]]
            aug_t_intervals = [aug_t.exon_intervals[0], aug_t.exon_intervals[-1]]
            for interval in merged_t_intervals:
                if seq_lib.interval_not_within_wiggle_room_intervals(aug_t_intervals, interval, wiggle_room):
                    bed_rec = interval.get_bed(self.rgb, "/".join([self.column, aug_aln_id]))
                    self.details_dict[aug_aln_id].append(bed_rec)
            if len(self.details_dict[aug_aln_id]) > 0:
                self.classify_dict[aug_aln_id] = 1
            else:
                self.classify_dict[aug_aln_id] = 0
        self.dump_results_to_disk()


class NotSameStart(AbstractAugustusClassifier):
    """
    Does the augustus transcript NOT have the exact same start bases as the transMap transcript?
    """
    @property
    def rgb(self):
        return self.colors["generic"]

    def run(self):
        for aug_aln_id, aug_t, t in self.augustus_transcript_transmap_iterator():
            if t.thick_start != aug_t.thick_start:
                s = aug_t.cds_size
                bed_rec = seq_lib.cds_coordinate_to_bed(aug_t, 0, 3, self.rgb, self.column)
                self.details_dict[aug_aln_id].append(bed_rec)
                self.classify_dict[aug_aln_id] = 1
            else:
                self.classify_dict[aug_aln_id] = 0
        self.dump_results_to_disk()


class NotSameStop(AbstractAugustusClassifier):
    """
    Does the augustus transcript NOT have the exact same stop bases as the transMap transcript?
    """
    @property
    def rgb(self):
        return self.colors["generic"]

    def run(self):
        for aug_aln_id, aug_t, t in self.augustus_transcript_transmap_iterator():
            if t.thick_stop != aug_t.thick_stop:
                s = aug_t.cds_size
                bed_rec = seq_lib.cds_coordinate_to_bed(aug_t, s - 3, s, self.rgb, self.column)
                self.details_dict[aug_aln_id].append(bed_rec)
                self.classify_dict[aug_aln_id] = 1
            else:
                self.classify_dict[aug_aln_id] = 0
        self.dump_results_to_disk()