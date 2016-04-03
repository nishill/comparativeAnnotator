"""
Constructs the database schema for this project.
"""
import os
from peewee import *
from pycbio.sys.introspection import classes_in_module
from pycbio.sys.fileOps import ensureDir
import comparativeAnnotator.classifiers as ref_classifiers
import comparativeAnnotator.alignment_classifiers as alignment_classifiers
import comparativeAnnotator.augustus_classifiers as augustus_classifiers
import comparativeAnnotator.alignment_attributes as alignment_attributes


database = SqliteDatabase(None)


class Base(Model):
    class Meta:
        database = database


class ReferenceAttributes(Base):
    """
    Reference attributes table has a fixed set of fields based on the 5 input TSV fields and 2 additional fields.
    """
    TranscriptId = TextField(primary_key=True)
    TranscriptType = TextField()
    GeneId = TextField()
    GeneName = TextField()
    GeneType = TextField()
    NumberIntrons = IntegerField()
    SourceChrom = TextField()
    SourceStart = IntegerField()
    SourceStop = IntegerField()
    SourceStrand = TextField()


class ReferenceGenome(Base):
    """
    Classifications/Details fields for the reference genome.
    """
    TranscriptId = TextField(primary_key=True)


class AlignmentAttributes(Base):
    """
    Base class for alignment attributes for a aligned genome.
    """
    AlignmentId = TextField(primary_key=True)
    TranscriptId = TextField()
    Paralogy = IntegerField(null=True)
    HighestCovAln = BooleanField(null=True)
    HighestIdentAln = BooleanField(null=True)
    BestOverallAln = BooleanField(null=True)


class GenomeClassify(Base):
    """
    Base table definition for a classify table.
    """
    AlignmentId = TextField(primary_key=True)
    TranscriptId = TextField()


class GenomeDetails(Base):
    """
    Base table definition for a details table.
    """
    AlignmentId = TextField(primary_key=True)
    TranscriptId = TextField()


class AugustusAttributes(Base):
    """
    Base class for alignment attributes for a aligned genome.
    """
    AugustusAlignmentId = TextField(primary_key=True)
    AlignmentId = TextField()
    TranscriptId = TextField()
    AugustusAlignmentCoverage = FloatField(null=True)
    AugustusAlignmentIdentity = FloatField(null=True)
    AugustusNumberIntrons = IntegerField(null=True)


class AugustusClassify(Base):
    """
    Base table definition for a classify table.
    """
    AugustusAlignmentId = TextField(primary_key=True)
    AlignmentId = TextField()
    TranscriptId = TextField()
    AugustusParalogy = IntegerField(null=True)


class AugustusDetails(Base):
    """
    Base table definition for a details table.
    """
    AugustusAlignmentId = TextField(primary_key=True)
    AlignmentId = TextField()
    TranscriptId = TextField()


class TableHolder(object):
    """
    Convenience namespace that holds table definitions. Extended to have a method to return them as a list or as an
    iterable.
    """
    @property
    def tables(self):
        return self.__dict__.values()

    def __iter__(self):
        for t in self.tables:
            yield t


def classify_columns(classifiers, dtype=None):
    """
    Builds a dictionary mapping columns to col_type. If dtype is set, force columns to that type.
    """
    if dtype is None:
        return {x.__name__: x.dtype(null=True) for x in classifiers}
    else:
        return {x.__name__: dtype(null=True) for x in classifiers}


def set_name(model, name):
    """
    Dynamically set the name for a peewee model class.
    """
    setattr(model._meta, 'db_table', name)


def build_namespace(attrs, classify, details):
    """
    Make a pretty clean namespace for the tree tables for
    """
    n = TableHolder()
    n.attrs = attrs
    n.classify = classify
    n.details = details
    return n


def ref_tables(ref_genome):
    """
    Constructs Attributes, Classify and Details tables for the reference genome.
    """
    # define table names
    attr_table_name = ref_genome + '_Attributes'
    classify_table_name = ref_genome + '_Classify'
    details_table_name = ref_genome + '_Details'
    # construct attributes table
    attrs = type(attr_table_name, (ReferenceAttributes,), {})
    set_name(attrs, attr_table_name)
    # construct classify table
    ref_classify_columns = classify_columns(classes_in_module(ref_classifiers), IntegerField)
    classify = type(classify_table_name, (ReferenceGenome,), ref_classify_columns)
    set_name(classify, classify_table_name)
    # construct details table
    ref_details_columns = classify_columns(classes_in_module(ref_classifiers), TextField)
    details = type(details_table_name, (ReferenceGenome,), ref_details_columns)
    set_name(details, details_table_name)
    return build_namespace(attrs, classify, details)


def tgt_tables(genome):
    """
    Constructs Attributes, Classify and Details tables for the reference genome.
    """
    # define table names
    attr_table_name = genome + '_Attributes'
    classify_table_name = genome + '_Classify'
    details_table_name = genome + '_Details'
    # construct attributes table
    aln_attr_columns = classify_columns(classes_in_module(alignment_attributes))
    attrs = type(attr_table_name, (AlignmentAttributes,), aln_attr_columns)
    set_name(attrs, attr_table_name)
    # construct classify table
    classifiers = classes_in_module(ref_classifiers) + classes_in_module(alignment_classifiers)
    ref_classify_columns = classify_columns(classifiers, IntegerField)
    classify = type(classify_table_name, (GenomeClassify,), ref_classify_columns)
    set_name(classify, classify_table_name)
    # construct details table
    ref_details_columns = classify_columns(classifiers, TextField)
    details = type(details_table_name, (GenomeDetails,), ref_details_columns)
    set_name(details, details_table_name)
    return build_namespace(attrs, classify, details)


def aug_tables(genome):
    """
    Constructs Attributes, Classify and Details tables for the reference genome.
    """
    # define table names
    attr_table_name = genome + '_AugustusAttributes'
    classify_table_name = genome + '_AugustusClassify'
    details_table_name = genome + '_AugustusDetails'
    # construct attributes table
    attrs = type(attr_table_name, (AugustusAttributes,), {})
    set_name(attrs, attr_table_name)
    # construct classify table
    classifiers = classes_in_module(augustus_classifiers)
    ref_classify_columns = classify_columns(classifiers, IntegerField)
    classify = type(classify_table_name, (AugustusClassify,), ref_classify_columns)
    set_name(classify, classify_table_name)
    # construct details table
    ref_details_columns = classify_columns(classifiers, TextField)
    details = type(details_table_name, (AugustusDetails,), ref_details_columns)
    set_name(details, details_table_name)
    return build_namespace(attrs, classify, details)


def initialize_tables(tables, db):
    """
    Initialize tables, dropping if they exist.
    """
    ensureDir(os.path.dirname(db))
    database.init(db)
    database.drop_tables(tables, safe=True)
    database.create_tables(tables)


def fetch_database():
    """
    Get database object associated with these tables
    """
    return database
