"""
This file configures the plotting and queries for the comparativeAnnotator pipeline.
"""


__author__ = "Ian Fiddes"


# Below are global variables shared by plotting scripts

# paired_palette has two parallel color spectrums and black as the outgroup color
paired_palette = ["#df65b0", "#dd1c77", "#980043",  # reds
                  "#a1dab4", "#41b6c4", "#2c7fb8",  # blues
                  "#252525", "#B24000"]  # brown and black

# triple palette is the same as paired palette but with 3 colors
triple_palette = ['#374a69', '#415e8c', '#4c72b0',  # blues
                  '#73383a', '#9b4346', '#c44e52',  # reds
                  '#3b6545', '#488656', '#55a868',  # greens
                  "#252525"]

# palette is the seaborn colorbind palette
palette = ["#0072b2", "#009e73", "#d55e00", "#cc79a7", "#f0e442", "#56b4e9"]


# list of classifiers in modules. TODO: I used to be able to import these, but now that leads to a circular import.
# too lazy to fix this at this point.

ref_classifiers = ['EndStop', 'BadFrame', 'CdsGap', 'UtrNonCanonSplice', 'CdsMult3Gap', 'BeginStart',
                   'SpliceContainsUnknownBases', 'UnknownGap', 'UnknownBases', 'CdsUnknownSplice', 'UtrUnknownSplice',
                   'UnknownCdsBases', 'UtrGap', 'StartOutOfFrame', 'CdsNonCanonSplice', 'InFrameStop', 'ShortCds']

all_classifiers = ref_classifiers + ['AlnExtendsOffContig', 'CodingMult3Deletions', 'Paralogy', 'HasOriginalIntrons',
                                     'AlnAbutsUnknownBases', 'CodingInsertions', 'AlignmentPartialMap', 'Synonymous',
                                     'FrameShift', 'HasOriginalStop', 'CodingMult3Insertions', 'CodingDeletions',
                                     'Nonsynonymous', 'HasOriginalStart']

# these classifiers define Pass for Augustus transcripts
aug_classifiers = ['MultipleTranscripts', 'NotSameStart', 'NotSameStop',
                   'ExonGain', 'NotSameStrand',
                   'NotSimilarTerminalExonBoundaries', 'ExonLoss',
                   'NotSimilarInternalExonBoundaries']

# these classifiers define Pass for single-genome analysis
ref_coding_classifiers = ["BadFrame", "BeginStart", "EndStop", "CdsGap", "CdsUnknownSplice", "UtrUnknownSplice",
                          "StartOutOfFrame", "SpliceContainsUnknownBases", "InFrameStop", "ShortCds"]

# these classifiers define Pass for coding transcripts
tm_pass_classifiers = ["BadFrame", "BeginStart", "EndStop", "CdsGap", "CdsUnknownSplice", "UtrUnknownSplice",
                       "StartOutOfFrame", "InFrameStop", "ShortCds", "CodingInsertions", "CodingDeletions",
                       "FrameShift", "HasOriginalStart", "HasOriginalStop", "HasOriginalIntrons"]

# these classifiers define Good for coding transcripts
# the difference: Can have an incomplete CDS, but that incomplete CDS should remain in frame. UtrUnknownSplice is also
# allowed.
tm_good_classifiers = ["CdsUnknownSplice", "FrameShift", "CodingInsertions", "CodingDeletions", "HasOriginalIntrons"]

# these classifiers define Pass/Good for non-coding transcripts
noncoding_pass_classifiers = ref_noncoding_classifiers = ["UtrUnknownSplice"]
noncoding_good_classifiers = ["UtrUnknownSplice", "UtrGap"]


clustering_classifiers = tm_pass_classifiers + ["AlnExtendsOffContig", "CodingMult3Deletions", "Paralogy", 
                                                "AlnAbutsUnknownBases", "CodingMult3Insertions", "CdsMult3Gap", 
                                                "SpliceContainsUnknownBases", "UnknownGap", "UnknownBases", 
                                                "UnknownCdsBases", "UtrGap", "AlignmentPartialMap"]


def refClassifiers(genome):
    base_query = "SELECT {} FROM details.'{}'"
    query = base_query.format(",".join(ref_classifiers), genome)
    return query


def allClassifiers(genome):
    base_query = "SELECT {} FROM details.'{}'"
    query = base_query.format(",".join(all_classifiers), genome)
    return query


def allClassifiers(genome):
    base_query = "SELECT {} FROM augustus_details.'{}'"
    query = base_query.format(",".join(aug_classifiers), genome)
    return query


def potentiallyInterestingBiology(genome):
    query = ("SELECT details.'{0}'.InFrameStop,details.'{0}'.CodingMult3Insertions,details.'{0}'."
             "CodingMult3Deletions,details.'{0}'.Nonsynonymous,details.'{0}'.FrameShift FROM details.'{0}' "
             "JOIN main.'{0}' USING ('AlignmentId') JOIN attributes.'{0}' USING ('AlignmentId') "
             "WHERE main.'{0}'.BadFrame = 0 AND main.'{0}'.BeginStart "
             "= 0 AND main.'{0}'.EndStop = 0 AND main.'{0}'.CdsGap = 0 AND main.'{0}'.CdsUnknownSplice = 0 "
             "AND main.'{0}'.UtrUnknownSplice = 0 AND main.'{0}'.StartOutOfFrame = 0 AND "
             "main.'{0}'.InFrameStop = 0 AND main.'{0}'.ShortCds = 0 AND main.'{0}'.CodingInsertions = 0 "
             "AND main.'{0}'.CodingDeletions = 0 AND main.'{0}'.FrameShift = 0 AND "
             "main.'{0}'.HasOriginalStart = 0 AND main.'{0}'.HasOriginalStop = 0 AND "
             "main.'{0}'.HasOriginalIntrons <= 0.5 * attributes.'{0}'.NumberIntrons - 0.5")
    query = query.format(genome)
    return query


def assemblyErrors(genome, biotype=None, details=True):
    query = (" FROM attributes.'{0}' JOIN details.'{0}' USING ('AlignmentId') JOIN main.'{0}' USING ('AlignmentId') "
             "WHERE main.'{0}'.AlignmentPartialMap > 0 OR main.'{0}'.UnknownBases > 0 OR main.'{0}'.UnknownGap > 0 "
             "OR main.'{0}'.ShortCds > 0 OR main.'{0}'.AlnAbutsUnknownBases > 0 OR main.'{0}'.AlnExtendsOffContig = 1")
    if details is True:
        query = ("SELECT details.'{0}'.AlignmentPartialMap,details.'{0}'.UnknownBases,details.'{0}'.UnknownGap,details."
                 "'{0}'.ShortCds,details.'{0}'.AlnAbutsUnknownBases,details.'{0}'.AlnExtendsOffContig ") + query
    else:
        query = "SELECT main.'{0}'.AlignmentId " + query
    if biotype is not None:
        query += " AND attributes.'{0}'.TranscriptType = '{1}' AND attributes.'{0}'.GeneType = '{1}'"
        query = query.format(genome, biotype)
    else:
        query = query.format(genome)
    return query


def alignmentErrors(genome, biotype=None, details=True):
    query = (" FROM attributes.'{0}' JOIN details.'{0}' USING ('AlignmentId') JOIN main.'{0}' USING "
             "('AlignmentId') WHERE main.'{0}'.BadFrame > 0 OR main.'{0}'.CdsGap > 0 OR "
             "main.'{0}'.CdsMult3Gap > 0 OR main.'{0}'.UtrGap > 0 OR main.'{0}'.Paralogy > 0 OR "
             "main.'{0}'.HasOriginalIntrons >= 0.5 * attributes.'{0}'.NumberIntrons - 0.5 OR "
             "main.'{0}'.StartOutOfFrame = 1")
    if details is True:
        query = ("SELECT details.'{0}'.BadFrame,details.'{0}'.CdsGap,details.'{0}'.CdsMult3Gap,"
                 "details.'{0}'.UtrGap,details.'{0}'.Paralogy,details.'{0}'.HasOriginalIntrons,"
                 "details.'{0}'.StartOutOfFrame") + query
    else:
        query = "SELECT main.'{0}'.AlignmentId " + query
    if biotype is not None:
        query += " AND attributes.'{0}'.TranscriptType = '{1}' AND attributes.'{0}'.GeneType = '{1}'"
        query = query.format(genome, biotype)
    else:
        query = query.format(genome)
    return query


def transMapEval(ref_genome, genome, biotype, good=False):
    if biotype == "protein_coding" and good is False:
        query = ("SELECT AlignmentId FROM attributes.'{2}' JOIN main.'{2}' USING (TranscriptId) JOIN "
                 "attributes.'{0}' USING (TranscriptId) JOIN main.'{0}' USING (AlignmentId) WHERE NOT "
                 "(main.'{2}'.BadFrame = 0 AND main.'{0}'.BadFrame > 0) AND NOT (main.'{2}'.BeginStart = 0 "
                  "AND main.'{0}'.BeginStart > 0) AND NOT (main.'{2}'.EndStop = 0 AND main.'{0}'.EndStop > 0) "
                  "AND NOT (main.'{2}'.CdsGap = 0 AND main.'{0}'.CdsGap > 0) AND NOT (main.'{2}'.CdsUnknownSplice"
                  " = 0 AND main.'{0}'.CdsUnknownSplice > 0) AND NOT (main.'{2}'.UtrUnknownSplice = 0 AND "
                  "main.'{0}'.UtrUnknownSplice > 0) AND NOT (main.'{2}'.StartOutOfFrame = 0 AND "
                  "main.'{0}'.StartOutOfFrame > 0) AND NOT (main.'{2}'.InFrameStop = 0 AND "
                  "main.'{0}'.InFrameStop > 0) AND NOT (main.'{2}'.ShortCds = 0 AND main.'{0}'.ShortCds > 0) AND "
                  "main.'{0}'.CodingInsertions = 0 AND main.'{0}'.CodingDeletions = 0 AND main.'{0}'.FrameShift = 0 "
                  "AND main.'{0}'.HasOriginalStop = 0 AND attributes.'{0}'.AlignmentCoverage = 100.0 AND "
                  "attributes.'{0}'.PercentUnknownBases <= 1.0 AND attributes.'{0}'.PercentUnknownCodingBases <= 0.2 "
                  "AND main.'{0}'.HasOriginalIntrons <= 0.5 * attributes.'{0}'.NumberIntrons - 0.5 AND "
                  "attributes.'{0}'.TranscriptType = '{1}' AND attributes.'{0}'.GeneType = '{1}'")
    elif biotype == "protein_coding" and good is True:
        query = ("SELECT AlignmentId FROM attributes.'{2}' JOIN main.'{2}' USING (TranscriptId) JOIN "
                 "attributes.'{0}' USING (TranscriptId) JOIN main.'{0}' USING (AlignmentId) WHERE NOT "
                 "(main.'{2}'.CdsUnknownSplice = 0 AND main.'{0}'.CdsUnknownSplice > 0) AND "
                 "main.'{0}'.FrameShift = 0 AND main.'{0}'.CodingInsertions = 0 AND main.'{0}'.CodingDeletions = 0 "
                 "AND attributes.'{0}'.AlignmentCoverage >= 95.0 AND "
                 "attributes.'{0}'.PercentUnknownBases <= 5.0 AND attributes.'{0}'.PercentUnknownCodingBases <= 1.0 "
                 "AND main.'{0}'.HasOriginalIntrons <= 0.5 * attributes.'{0}'.NumberIntrons - 0.5 AND "
                 "attributes.'{0}'.TranscriptType = '{1}' AND attributes.'{0}'.GeneType = '{1}'")
    elif good is False:
        query = ("SELECT AlignmentId FROM attributes.'{2}' JOIN main.'{2}' USING (TranscriptId) JOIN "
                 "attributes.'{0}' USING (TranscriptId) JOIN main.'{0}' USING (AlignmentId) WHERE NOT "
                 "(main.'{2}'.UtrUnknownSplice = 0 AND main.'{0}'.UtrUnknownSplice > 0) AND "
                 "attributes.'{0}'.AlignmentCoverage = 100.0 AND attributes.'{0}'.PercentUnknownBases <= 1.0 AND "
                 "main.'{0}'.HasOriginalIntrons <= 0.5 * attributes.'{0}'.NumberIntrons - 0.5 AND "
                 "attributes.'{0}'.TranscriptType = '{1}' AND attributes.'{0}'.GeneType = '{1}'")
    else:
        query = ("SELECT AlignmentId FROM attributes.'{2}' JOIN main.'{2}' USING (TranscriptId) JOIN "
                 "attributes.'{0}' USING (TranscriptId) JOIN main.'{0}' USING (AlignmentId) WHERE NOT "
                 "(main.'{2}'.UtrUnknownSplice = 0 AND main.'{0}'.UtrUnknownSplice > 0) AND "
                 "main.'{0}'.UtrGap = 0 AND attributes.'{0}'.AlignmentCoverage >= 95.0 AND "
                 "main.'{0}'.HasOriginalIntrons <= 0.5 * attributes.'{0}'.NumberIntrons - 0.5 AND "
                 "attributes.'{0}'.PercentUnknownBases <= 5.0 AND attributes.'{0}'.TranscriptType = '{1}' AND "
                 "attributes.'{0}'.GeneType = '{1}'")
    
    query = query.format(genome, biotype, ref_genome)
    return query


def refEval(genome):
    query = ("SELECT TranscriptId FROM main.'{}' WHERE BadFrame = 0 AND BeginStart = 0 AND EndStop = 0 AND CdsGap = 0 "
             "AND CdsUnknownSplice = 0 AND UtrUnknownSplice = 0 AND StartOutOfFrame = 0 AND "
             "SpliceContainsUnknownBases = 0 AND InFrameStop = 0 AND ShortCds = 0")
    query = query.format(genome)
    return query


def augustusEval(genome, ref_genome):
    query = ("SELECT augustus.'{0}'.AlignmentId FROM attributes.'{1}' JOIN main.'{1}' USING (TranscriptId) "
             "JOIN attributes.'{0}' USING (TranscriptId) JOIN main.'{0}' USING (AlignmentId) JOIN "
             "augustus_attributes.'{0}' ON main.'{0}'.AlignmentId = augustus_attributes.'{0}'.AlignmentId JOIN "
             "augustus.'{0}' USING (AlignmentId) WHERE (NotSameStart = 0 OR "
             "(main.'{0}'.HasOriginalStart = 1 OR main.'{0}'.StartOutOfFrame = 1 OR main.'{0}'.BadFrame = 1 OR "
             "main.'{1}'.BeginStart = 1)) AND (NotSameStop = 0 OR (main.'{0}'.HasOriginalStop = 1 OR "
             "main.'{0}'.BadFrame = 1 OR main.'{1}'.EndStop = 1)) AND (NotSimilarTerminalExonBoundaries = 0 "
             "OR (attributes.'{0}'.AlignmentCoverage < 95.0 OR main.'{0}'.UtrGap > 3)) AND "
             "(NotSimilarInternalExonBoundaries = 0 OR (main.'{0}'.CdsGap > 3 OR main.'{0}'.UtrGap > 3 OR "
             "main.'{1}'.CdsUnknownSplice > 0 OR main.'{1}'.UtrUnknownSplice > 0))  AND NotSameStrand = 0 AND "
             "ExonLoss = 0 AND MultipleTranscripts = 0")
    query = query.format(genome, ref_genome)
    return query
