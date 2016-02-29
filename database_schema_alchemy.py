"""
Generates table objects for SQLAlchemy describing the table schema.
Deprecated for now in favor of peewee
"""
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from pycbio.sys.introspection import classes_in_module
import comparativeAnnotator.classifiers as ref_classifiers
import comparativeAnnotator.alignment_classifiers as aln_classifiers
import comparativeAnnotator.alignment_attributes as aln_attributes

__author__ = "Ian Fiddes"

Base = declarative_base()


def base_attributes(genome):
    """
    Returns a dictionary defining the base columns for an attributes table.
    """
    return {'TranscriptId': Column(String, primary_key=True), '__tablename__': genome + '_Attributes',
            'GeneName': Column(String), 'GeneType': Column(String), 'TranscriptType': Column(String),
            'NumberIntrons': Column(Integer), 'GeneId': Column(String)}


def classify_columns(classifiers, dtype=None):
    """
    Builds a dictionary mapping columns to col_type. If dtype is set, force columns to that type.
    """
    if dtype is None:
        return {x.__name__: Column(x.dtype) for x in classifiers}
    else:
        return {x.__name__: Column(dtype) for x in classifiers}


def add_tablename_primary(d, primary_name, tablename):
    """
    Adds primarykey and tablename to a dictionary defining a table.
    """
    d[primary_name] = Column(String, primary_key=True)
    d['__tablename__'] = tablename


def construct_ref_tables(ref_genome):
    """
    Constructs database tables for the reference. Produces the classification, details and attributes tables.
    """
    # attributes table
    attr_name = ref_genome + '_Attributes'
    attr_cols = base_attributes(ref_genome)
    add_tablename_primary(attr_cols, 'TranscriptId', attr_name)
    ref_attributes = type(attr_name, (Base,), attr_cols)
    # classification table for reference classifiers
    classify_name = ref_genome + '_Classify'
    classifiers = classes_in_module(ref_classifiers)
    classify_cols = classify_columns(classifiers, dtype=Integer)
    add_tablename_primary(classify_cols, 'TranscriptId', classify_name)
    ref_classify = type(ref_genome + '_Classify', (Base,), classify_cols)
    # matching details table that contains BED records
    details_name = ref_genome + '_Details'
    details_cols = classify_columns(classifiers, dtype=String)
    add_tablename_primary(details_cols, 'TranscriptId', details_name)
    ref_details = type(details_name, (Base,), details_cols)
    return ref_classify, ref_details, ref_attributes


def construct_tm_tables(ref_genome, genome):
    """
    Constructs database tables for an aligned genome. Produces the classification, details and attributes tables.
    """
    # construct the reference tables so we can refer to them
    ref_classify, ref_details, ref_attributes = construct_ref_tables(ref_genome)
    attr_name = genome + '_Attributes'
    attr_cols = classify_columns(classes_in_module(aln_attributes))
    add_tablename_primary(attr_cols, 'AlignmentId', attr_name)
    tgt_attributes = type(attr_name, (Base,), attr_cols)
    # classification table
    classify_name = genome + '_Classify'
    classifiers = classes_in_module(ref_classifiers) + classes_in_module(aln_classifiers)
    classify_cols = classify_columns(classifiers, dtype=Integer)
    add_tablename_primary(classify_cols, 'AlignmentId', classify_name)
    tgt_classify = type(classify_name, (Base,), classify_cols)
    # matching details table that contains BED records
    details_name = genome + '_Details'
    details_cols = classify_columns(classifiers, dtype=String)
    add_tablename_primary(details_cols, 'AlignmentId', details_name)
    tgt_details = type(details_name, (Base,), details_cols)
    return ref_classify, ref_details, ref_attributes, tgt_classify, tgt_details, tgt_attributes
