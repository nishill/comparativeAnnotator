import re
from itertools import izip

from lib.general_lib import formatRatio
from src.abstractClassifier import AbstractClassifier

import lib.sequence_lib as seq_lib
import lib.psl_lib as psl_lib
import lib.sqlite_lib as sql_lib


class CodingInsertions(AbstractClassifier):
    """

    Does the alignment introduce insertions that are not a multiple of 3 to the target genome?

    reports 1 (TRUE) if so, 0 (FALSE) otherwise

    Target insertion:

    query:   AATTAT--GCATGGA
    target:  AATTATAAGCATGGA

    """

    @staticmethod
    def _getType():
        return "INTEGER"

    def analyzeExons(self, transcript, aln, mult3=False):
        """
        Analyze a Transcript object for coding insertions.
        if mult3 is True, only multiple of 3 insertions are reported.
        """
        insertFlag = False
        for exon in transcript.exons:
            for i in xrange(exon.start, exon.stop):
                #we have found an insertion
                if insertFlag is False and aln.queryCoordinateToTarget(i) == None:
                    insertSize = 1
                    insertFlag = True
                #insertion continues
                elif insertFlag is True and aln.queryCoordinateToTarget(i) == None:
                    insertSize += 1
                #exiting insertion
                elif insertFlag is True and aln.queryCoordinateToTarget(i) != None:
                    if (transcript.transcriptCoordinateToCds(i) is not None or 
                            transcript.transcriptCoordinateToCds(i + insertSize) is not None):
                        if insertSize % 3 == 0 and mult3 == True:
                            return 1
                        elif insertSize % 3 != 0 and mult3 == False:
                            return 1
                    insertSize = 0
                    insertFlag = False
        return 0

    def run(self, mult3=False):
        self.getAnnotationDict()
        self.getAlignmentDict()
        self.getTranscriptDict()
        valueDict = {}
        for aId, aln in self.alignmentDict.iteritems():
            if aId not in self.transcriptDict:
                continue
            #annotated transcript coordinates are the same as query coordinates (they are the query)
            annotatedTranscript = self.annotationDict[psl_lib.removeAlignmentNumber(aId)]
            valueDict[aId] = self.analyzeExons(annotatedTranscript, aln, mult3)
        self.simpleUpdateWrapper(valueDict)


class CodingMult3Insertions(CodingInsertions):
    """

    See CodingInsertions. Reports all cases where there are multiple of 3 insertions.

    """

    def run(self):
        CodingInsertions.run(self, mult3=True)


class CodingDeletions(AbstractClassifier):
    """

    Does the alignment introduce deletions that are not a multiple of 3 to the target genome?

    reports 1 (TRUE) if so, 0 (FALSE) otherwise

    query:   AATTATAAGCATGGA
    target:  AATTAT--GCATGGA
             012345  67
    """

    @staticmethod
    def _getType():
        return "INTEGER"

    def analyzeExons(self, t, aln, mult3=False):
        delFlag = False
        for exon in t.exons:
            for i in xrange(exon.start, exon.stop):
                chrom_i = t.transcriptCoordinateToChromosome(i)
                #entering deletion
                if delFlag is False and aln.targetCoordinateToQuery(chrom_i) is None:
                    delSize = 1
                    delFlag = True
                #continuing deletion
                elif delFlag is True and aln.targetCoordinateToQuery(chrom_i) is None:
                    delSize += 1
                #exiting deletion
                elif delFlag is True and aln.targetCoordinateToQuery(chrom_i) is not None:
                    if t.chromosomeCoordinateToCds(chrom_i) is not None:
                        if delSize % 3 == 0 and mult3 is True:
                            return 1
                        elif delSize % 3 != 0 and mult3 is False:
                            return 1
        return 0

    def run(self, mult3=False):
        self.getAlignmentDict()
        self.getTranscriptDict()
        valueDict = {}
        for aId, aln in self.alignmentDict.iteritems():
            if aId not in self.transcriptDict:
                continue
            transcript = self.transcriptDict[aId]
            valueDict[aId] = self.analyzeExons(transcript, aln, mult3)
        self.simpleUpdateWrapper(valueDict)


class CodingMult3Deletions(CodingDeletions):
    """

    See CodingDeletions. Reports all cases where there are multiple of 3 insertions.

    """

    def run(self):
        CodingDeletions.run(self, mult3=True)


class AlignmentAbutsLeft(AbstractClassifier):
    """

    Does the alignment extend off the 3' end of a scaffold?
    (regardless of transcript orientation)

    aligned: #  unaligned: -  whatever: .  edge: |
             query  |---#####....
             target    |#####....

    Entries are either 1 (TRUE) or 0 (FALSE)

    """

    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self):
        self.getAlignmentDict()
        valueDict = {}
        for aId, aln in self.alignmentDict.iteritems():
            if aln.strand == "+" and aln.tStart == 0 and aln.qStart != 0:
                valueDict[aId] = 1
            elif aln.strand == "-" and aln.tEnd == aln.tSize and aln.qEnd != aln.qSize:
                valueDict[aId] = 1
            else:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class AlignmentAbutsRight(AbstractClassifier):
    """

    Does the alignment extend off the 3' end of a scaffold?
    (regardless of transcript orientation)

    aligned: #  unaligned: -  whatever: .  edge: |
             query  ...######---|
             target ...######|

    Entries are either 1 (TRUE) or 0 (FALSE)

    """

    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self):
        self.getAlignmentDict()
        valueDict = {}
        for aId, aln in self.alignmentDict.iteritems():
            if aln.strand == "+" and aln.tEnd == aln.tSize and aln.qEnd != aln.qSize:
                valueDict[aId] = 1
            elif aln.strand == "-" and aln.tStart == 0 and aln.qStart != 0:
                valueDict[aId] = 1
            else:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class AlignmentCoverage(AbstractClassifier):
    """

    Calculates alignment coverage:

    (matches + mismatches) / (matches + mismatches + query_insertions)

    Reports the value as a REAL between 0 and 1

    """

    @staticmethod
    def _getType():
        return "REAL"

    def run(self):
        self.getAlignmentDict()
        valueDict = {}
        for aId, aln in self.alignmentDict.iteritems():
            valueDict[aId] = formatRatio(aln.matches + aln.misMatches, aln.matches + aln.misMatches 
                    + aln.qNumInsert)
        self.simpleUpdateWrapper(valueDict)


class AlignmentIdentity(AbstractClassifier):
    """

    Calculates alignment identity:

    matches / (matches + mismatches + query_insertions)

    Reports the value as a REAL between 0 and 1

    """

    @staticmethod
    def _getType():
        return "REAL"

    def run(self):
        self.getAlignmentDict()
        valueDict = {}
        for aId, aln in self.alignmentDict.iteritems():
            valueDict[aId] = formatRatio(aln.matches, aln.matches + aln.misMatches + aln.qNumInsert)
        self.simpleUpdateWrapper(valueDict)


class AlignmentPartialMap(AbstractClassifier):
    """

    Does the query sequence NOT map entirely?

    a.qSize != a.qEnd - a.qStart

    Reports 1 if TRUE and 0 if FALSE

    """

    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self):
        self.getAlignmentDict()
        valueDict = {}
        for aId, aln in self.alignmentDict.iteritems():
            if aln.qSize != aln.qEnd - aln.qStart:
                valueDict[aId] = 1
            else:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class BadFrame(AbstractClassifier):
    """

    Looks for CDS sequences that are not a multiple of 3

    Reports 1 if TRUE and 0 if FALSE

    """

    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self):
        self.getAlignmentDict()
        self.getTranscriptDict()
        valueDict = {}
        for aId, aln in self.alignmentDict.iteritems():        
            if aId not in self.transcriptDict:
                continue
            t = self.transcriptDict[aId]
            if t.getCdsLength() % 3 != 0:
                valueDict[aId] = 1
            else:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class BeginStart(AbstractClassifier):
    """

    Does the annotated CDS have a start codon (ATG) in the first 3 bases?

    Returns 1 if TRUE 0 if FALSE

    Value will be NULL if there is unsufficient information, which is defined as:
        1) thickStart == thickStop == 0 (no CDS)
        2) thickStop - thickStart < 3: (no useful CDS annotation)
        3) this alignment was not trans-mapped

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self):
        self.getTranscriptDict()
        self.getSeqDict()
        valueDict = {}
        for aId in self.aIds:
            if aId not in self.transcriptDict:
                continue
            t = self.transcriptDict[aId]
            if t.thickStart == t.thickStop == 0 or t.thickStop - t.thickStart < 3:
                continue
            s = t.getCds(self.seqDict)
            if s.startswith("ATG"):
                valueDict[aId] = 1
            else:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class CdsGap(AbstractClassifier):
    """

    Are any of the CDS introns too short? Too short default is 30 bases.

    Returns 1 if TRUE 0 if FALSE

    If mult3 is true, will only report on multiple of 3 gaps.

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def mult3(self, t, shortIntronSize):
        #only report if CdsGap is a multiple of 3
        for i in xrange(len(t.intronIntervals)):
            #is this intron coding?
            if t.exons[i].containsCds() is True and t.exons[i+1].containsCds() is True:
                if len(t.intronIntervals[i]) <= shortIntronSize:
                    if len(t.intronIntervals[i]) % 3 == 0:
                        return 1
        return 0

    def notMult3(self, t, shortIntronSize):
        #only report if CdsGap is a multiple of 3
        for i in xrange(len(t.intronIntervals)):
            #is this intron coding?
            if t.exons[i].containsCds() is True and t.exons[i+1].containsCds() is True:
                if len(t.intronIntervals[i]) <= shortIntronSize:
                    if len(t.intronIntervals[i]) % 3 != 0:
                        return 1
        return 0
  
    def run(self, mult3=False, shortIntronSize=30):
        self.getTranscriptDict()
        valueDict = {}
        for aId in self.aIds:
            if aId not in self.transcriptDict:
                continue
            if mult3 is True:               
                valueDict[aId] = self.mult3(self.transcriptDict[aId], shortIntronSize)
            else:
                valueDict[aId] = self.notMult3(self.transcriptDict[aId], shortIntronSize)
        self.simpleUpdateWrapper(valueDict)
        

class CdsMult3Gap(CdsGap):
    """

    See CdsGap for details. Runs it in mult3 mode.

    """

    def run(self, mult3=True, shortIntronSize=30):
        CdsGap.run(self, mult3, shortIntronSize)


class CdsNonCanonSplice(AbstractClassifier):
    """

    Are any of the CDS introns splice sites not of the canonical form
    GT..AG

    reports 1 if TRUE, 0 if FALSE

    This classifier is only applied to introns which are longer than
    a minimum intron size.

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def badSplice(self, donor, acceptor):
        m = {"GT":"AG"}
        d = donor.upper()
        a = acceptor.upper()
        if d in m and m[d] != a:
            return True
        else:
            return False

    def run(self, shortIntronSize=30):
        self.getTranscriptDict()
        self.getSeqDict()
        valueDict = {}
        for aId in self.aIds:
            if aId not in self.transcriptDict:
                continue          
            t = self.transcriptDict[aId]
            for i, seq in enumerate(t.intronSequenceIterator(self.seqDict)):
                #make sure this intron is between coding exons
                if t.exons[i].containsCds() and t.exons[i+1].containsCds():
                    if self.badSplice(seq[:2], seq[-2:]) == True:
                        valueDict[aId] = 1
                        break
            if aId not in valueDict:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class CdsUnknownSplice(CdsNonCanonSplice):
    """

    Are any of the CDS introns splice sites not of the form
    GT..AG, GC..AG, AT..AC

    subclasses cdsNonCanonSplice and just replaces the badSplice function

    reports 1 if TRUE, 0 if FALSE

    This classifier is only applied to introns which are longer than
    a minimum intron size.

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def badSplice(self, donor, acceptor):
        m = {"GT":"AG", "GC":"AG", "AT":"AC"}
        d = donor.upper()
        a = acceptor.upper()
        if d in m and m[d] != a:
            return 1
        else:
            return 0

    def run(self, shortIntronSize=30):
        CdsNonCanonSplice.run(self)


class EndStop(AbstractClassifier):
    """

    Looks at the end of the coding region (thickEnd) and sees if the last
    three bases are a stop codon ('TAA', 'TGA', 'TAG')

    mode: Returns 1 if TRUE 0 if FALSE
    
    Value will be NULL if there is unsufficient information, which is defined as:
        1) thickStop - thickStart < 3: (no useful CDS annotation)
        2) this alignment was not trans-mapped

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self):
        stopCodons = ('TAA', 'TGA', 'TAG')
        self.getTranscriptDict()
        self.getSeqDict()
        valueDict = {}
        for aId in self.aIds:
            if aId not in self.transcriptDict:
                continue
            t = self.transcriptDict[aId]
            if t.thickStop - t.thickStart < 3:
                continue
            s = t.getCds(self.seqDict)[-3:]
            if s in stopCodons:
                valueDict[aId] = 1
            else:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class InFrameStop(AbstractClassifier):
    """

    Reports on in frame stop codons for each transcript.

    In order to be considered, must have at least 3 codons.

    mode: Reports 1 if TRUE (has in frame stop), 0 if FALSE

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self):
        self.getTranscriptDict()
        self.getSeqDict()
        valueDict = {}
        for aId in self.aIds:
            if aId not in self.transcriptDict:
                continue
            t = self.transcriptDict[aId]
            #make sure this transcript has CDS
            #and more than 2 codons - can't have in frame stop without that
            if t.getCdsLength() >= 9:
                for i in xrange(9, t.getCdsLength() - 3, 3):
                    c = t.cdsCoordinateToAminoAcid(i, self.seqDict)
                    if c == "*":
                        valueDict[aId] = 1
            if aId not in valueDict:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class NoCds(AbstractClassifier):
    """

    Looks to see if this transcript actually has a CDS, which is defined as having a
    thickStop-thickStart region of at least 1 codon. Adjusting cdsCutoff can change this.

    Reports a 1 if TRUE, 0 if FALSE.

    Only reports 1 if the original transcript had a CDS.

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self, cdsCutoff=3):
        self.getTranscriptDict()
        self.getAnnotationDict()
        valueDict = {}
        for aId in self.aIds:
            if aId not in self.transcriptDict:
                continue
            t = self.transcriptDict[aId]
            if t.getCdsLength() < cdsCutoff:
                a = self.annotationDict[psl_lib.removeAlignmentNumber(aId)]
                if a.getCdsLength() > cdsCutoff:
                    valueDict[aId] = 1
            else:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class MinimumCdsSize(NoCds):
    """

    The smallest ORFs in any species are >10AA. So, we will flag any CDS smaller than this.

    Inherits NoCds and modifies cdsCutoff to do this.

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self):
        NoCds.run(self, cdsCutoff=30)


class ScaffoldGap(AbstractClassifier):
    """

    Does this alignment span a scaffold gap? (Defined as a 100bp run of Ns)

    Reports 1 if TRUE, 0 if FALSE

    """

    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self):
        self.getAlignmentDict()
        self.getSeqDict()
        valueDict = {}
        r = re.compile("[N]{100}")
        for aId, aln in self.alignmentDict.iteritems():
            destSeq = self.seqDict[aln.tName][aln.tStart : aln.tEnd].upper()
            if re.search(r, destSeq) is not None:
                valueDict[aId] = 1
            else:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class UnknownBases(AbstractClassifier):
    """

    Does this alignment contain Ns in the target genome?

    Only looks mRNA bases, and restricts to CDS if cds is True

    Reports 1 if TRUE, 0 if FALSE

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self, cds=False):
        self.getTranscriptDict()
        self.getSeqDict()
        valueDict = {}
        for aId in self.aIds:
            if aId not in self.transcriptDict:
                continue
            t = self.transcriptDict[aId]
            if cds is True:
                s = t.getCds(self.seqDict)
            else:
                s = t.getMRna(self.seqDict)
            if "N" in s:
                valueDict[aId] = 1
            else:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class UnknownCdsBases(UnknownBases):
    """

    Inherits Unknown Bases and sets the cds flag to True.

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self):
        UnknownBases.run(self, cds=True)


class UtrGap(AbstractClassifier):
    """

    Are any UTR introns too short? Too short is defined as less than 30bp

    Reports 1 if TRUE, 0 if FALSE

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def run(self, shortIntronSize=30):
        self.getTranscriptDict()
        valueDict = {}
        for aId in self.aIds:
            if aId not in self.transcriptDict:
                continue
            t = self.transcriptDict[aId]
            for i in xrange(len(t.intronIntervals)):
                if t.exons[i].containsCds() is False and t.exons[i+1].containsCds() is False:
                    if len(t.intronIntervals[i]) <= shortIntronSize:
                        valueDict[aId] = 1
                        break
            if aId not in valueDict:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class UtrNonCanonSplice(AbstractClassifier):
    """

    Are any of the UTR introns splice sites not of the canonical form
    GT..AG

    reports 1 if TRUE, 0 if FALSE

    This classifier is only applied to introns which are longer than
    a minimum intron size.

    TODO: this class is nearly identical to CdsNonCanonSplice. Devise a way to merge.

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def badSplice(self, donor, acceptor):
        m = {"GT":"AG"}
        d = donor.upper()
        a = acceptor.upper()
        if d in m and m[d] != a:
            return 1
        else:
            return 0

    def run(self, shortIntronSize=30):
        self.getTranscriptDict()
        self.getSeqDict()
        valueDict = {}
        for aId in self.aIds:
            if aId not in self.transcriptDict:
                continue          
            t = self.transcriptDict[aId]
            for i, seq in enumerate(t.intronSequenceIterator(self.seqDict)):
                #make sure this intron is NOT between coding exons
                if not (t.exons[i].containsCds() and t.exons[i+1].containsCds()):
                    bad = self.badSplice(seq[:2], seq[-2:])
                    if bad == 1:
                        valueDict[aId] = 1
            if aId not in valueDict:
                valueDict[aId] = 0
        self.simpleUpdateWrapper(valueDict)


class UtrUnknownSplice(UtrNonCanonSplice):
    """

    Are any of the UTR introns splice sites not of the form
    GT..AG, GC..AG, AT..AC

    subclasses CdsNonCanonSplice and just replaces the badSplice function

    reports 1 if TRUE, 0 if FALSE

    This classifier is only applied to introns which are longer than
    a minimum intron size.

    """
    @staticmethod
    def _getType():
        return "INTEGER"

    def badSplice(self, donor, acceptor):
        m = {"GT":"AG", "GC":"AG", "AT":"AC"}
        d = donor.upper()
        a = acceptor.upper()
        if d in m and m[d] != a:
            return 1
        else:
            return 0

    def run(self, shortIntronSize=30):
        UtrNonCanonSplice.run(self)