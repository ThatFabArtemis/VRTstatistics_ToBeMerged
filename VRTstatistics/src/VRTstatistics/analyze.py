from __future__ import annotations
import fnmatch
from typing import List, Optional, Sequence
import pandas as pd
from .datastore import DataStoreError

__all__ = ["DataFrameFilter", "TileCombiner", "SessionTimeFilter"]


class DataFrameFilter:
    """A DataFrameFiler is a callable object that accepts a dataframe and returns a copy of that dataframe with filtering applied.
    
    DataFrameFilters can be added. This modifies the RHS filter to apply the LHS
    filter before itself and returns the RHS filter.
    
    Not elegant, but it means filters can be stacked left-to-right with +.
    """
    previous_filter : Optional[DataFrameFilter]

    def __init__(self):
        self.previous_filter = None

    def __add__(self, other : DataFrameFilter) -> DataFrameFilter:
        other.previous_filter = self
        return other

    def __call__(self, dataframe : pd.DataFrame) -> pd.DataFrame:
        if self.previous_filter:
            dataframe = self.previous_filter(dataframe)
        dataframe = self._apply(dataframe)
        return dataframe

    def _apply(self, dataframe : pd.DataFrame) -> pd.DataFrame:
        return dataframe

class SessionTimeFilter(DataFrameFilter):
    """
    DataFrameFilter that removes all items with sessiontime < 0
    """

    def _apply(self, dataframe : pd.DataFrame) -> pd.DataFrame:
        dataframe = dataframe[dataframe["sessiontime"] >= 0]
        return dataframe

class TileCombiner(DataFrameFilter):
    """
    DafaFrameFilter that combines columns matching a pattern into a new column.

    :param pattern: A (shell-like) pattern selecting one or more columns
    :type pattern: str
    :param column: name of the output column
    :type column: str
    :param function: Function to apply to the fields: sum/mean/max/min
    :type function: str
    :param combined: If True, the combined column is joined back onto the full original dataframe (all rows preserved). If False, only the rows that had values in the matched columns are returned.
    :type combined: bool
    :param keep: Keep the original columns selected by pattern, otherwise drop them.
    :type keep: bool
    :param optional: don't complain if pattern doesn't match anything, return the dataFrama as-is.
    :type optional: bool
    """

    def __init__(self, pattern : str, column : str, function : str, combined : bool = False, keep : bool = False, optional : bool = False) -> None:
        super().__init__()
        self.pattern = pattern
        self.column = column
        self.function = function
        self.combined = combined
        self.keep = keep
        self.optional = optional
        self.didwarn = False

    def _apply(self, dataframe : pd.DataFrame) -> pd.DataFrame:
        column_names = self._get_column_names(dataframe, self.pattern)
        if not column_names:
            if not self.optional and not self.didwarn:
                print(f'Warning: pattern {self.pattern} did not select any columns. Returning dataframe as-is.')
                self.didwarn = True
            return dataframe
        rv = None
        for n in column_names:
            # Create scaffolding (sessiontimes) if we haven't done so.
            filter = dataframe[n].notna()
            if rv is None:
                rv = dataframe[filter].copy()
                rv.drop(column_names, axis=1, inplace=True)
                # rv = rv["sessiontime"]
            # filter out values for this column
            c = dataframe.loc[filter, n]
            
            # Insert
            new_values = list(c)
            while len(new_values) < len(rv):
                new_values.append(0)
            while len(new_values) > len(rv):
                new_values = new_values[:-1]
            rv[n] = new_values
        # Now sum the relevant columns
        assert rv is not None
        if self.function == "sum":
            rv[self.column] = rv[column_names].sum(axis=1)
        elif self.function == "mean":
            rv[self.column] = rv[column_names].mean(axis=1)
        elif self.function == "min":
            rv[self.column] = rv[column_names].min(axis=1)
        elif self.function == "max":
            rv[self.column] = rv[column_names].max(axis=1)
        else:
            raise DataStoreError(f"Unknown function {self.function}")
        rv.drop(column_names, axis=1, inplace=True)
        if self.combined:
            orig_columns : List[str] = list(dataframe.keys())
            rv_columns : List[str] = list(rv.keys())
            todrop_columns : List[str] = []
            for c in orig_columns:
                if c in rv_columns:
                    todrop_columns.append(c)
            rv.drop(todrop_columns, axis=1, inplace=True)
            rv = dataframe.join(rv)
            if not self.keep:
                rv.drop(column_names, axis=1, inplace=True)
        return rv

    def _get_column_names(self, dataframe : pd.DataFrame, pattern : str) -> List[str]:
        """
        Return all column names in a DataFrame that match the given pattern
        
        :param dataframe: the DataFrame
        :type dataframe: pd.DataFrame
        :param pattern: A pattern. May contain * wildcards.
        :type pattern: str
        :return: List of column names matched.
        :rtype: List[str]
        """
        all_columns : List[str] = list(dataframe.keys())
        rv : List[str] = []
        for col in all_columns:
            if fnmatch.fnmatchcase(col, pattern):
                rv.append(col)
        return rv

def _df_to_pc_index_1(df : pd.DataFrame, column : str) -> pd.DataFrame:
    """Helper - convert a single column from time->index mapping into index->time mapping"""
    tmp : pd.DataFrame = df[["sessiontime", column]].dropna()
    filter = tmp[column] > 0
    tmp = tmp[filter].copy()
    tmp.loc[:,'pc_index'] = tmp[column]
    tmp[column+'.sessiontime'] = tmp['sessiontime']
    tmp.drop(['sessiontime', column], axis=1, inplace=True)
    tmp.set_index('pc_index', inplace=True)
    return tmp

def _df_to_pc_index(df : pd.DataFrame, columns : List[str]) -> pd.DataFrame:
    """Helper - convert a set of columns from sessiontime-indexed into pcindex-indexed"""
    all : Sequence[pd.DataFrame] = []
    for c in columns:
        all.append(_df_to_pc_index_1(df, c))
    rv = all[0]
    rv = rv.join(all[1:])
    return rv
    
def dataframe_to_pcindex_for_tile(dataframe : pd.DataFrame, tilenum : int, include_sender : bool=False, sender : str="sender", receiver : str="receiver") -> pd.DataFrame:
    """
    Re-index a progress dataframe from session-time rows to per-pointcloud rows for one tile.

    Input: a dataframe with sessiontime rows and aggregate_packets columns per pipeline stage
    (e.g. receiver.pc.reader.0, receiver.pc.decoder.0, receiver.pc.preparer.0).
    Each column value is a point-cloud sequence number; each row is when that stage
    reported receiving that sequence number.

    Output: a dataframe indexed by point-cloud sequence number, with one column per stage
    holding the session time when that stage received that point cloud.
    Stages that never received a given point cloud have NaN for that row.
    """
    cols = [
        f'{receiver}.pc.reader.{tilenum}',
        f'{receiver}.pc.decoder.{tilenum}',
        f'{receiver}.pc.preparer.{tilenum}'
        ]
    if include_sender:
        cols.insert(0, f'{sender}.pc.writer.{tilenum}')
    return _df_to_pc_index(dataframe, cols)

def dataframe_to_pcindex_latencies_for_tile(dataframe : pd.DataFrame, tilenum : int, sender : str="sender", receiver : str="receiver") -> pd.DataFrame:
    """
    For each point cloud received on one tile, compute how long after reader arrival each
    subsequent receiver stage (decoder, preparer) received that same point cloud.

    Input: same progress dataframe as dataframe_to_pcindex_for_tile.
    Output: a dataframe with one row per point cloud, columns:
      - sessiontime: when the reader received this point cloud (x-axis for plotting)
      - receiver.pc.decoder.{tilenum}.latency: seconds after reader arrival the decoder received it
      - receiver.pc.preparer.{tilenum}.latency: seconds after reader arrival the preparer received it

    Used by plot_progress_latency (in mmsys_2025; not yet in VRTstatistics — see issue #21).
    """
    rv = dataframe_to_pcindex_for_tile(dataframe, tilenum, include_sender=False, sender=sender, receiver=receiver)
    basecol = rv[f'{receiver}.pc.reader.{tilenum}.sessiontime']

    rv[f'{receiver}.pc.preparer.{tilenum}.latency'] = rv[f'{receiver}.pc.preparer.{tilenum}.sessiontime'] - basecol
    rv[f'{receiver}.pc.decoder.{tilenum}.latency'] = rv[f'{receiver}.pc.decoder.{tilenum}.sessiontime'] - basecol
    rv[f'sessiontime'] = rv[f'{receiver}.pc.reader.{tilenum}.sessiontime']
    rv.drop(f'{receiver}.pc.preparer.{tilenum}.sessiontime', axis=1, inplace=True)
    rv.drop(f'{receiver}.pc.decoder.{tilenum}.sessiontime', axis=1, inplace=True)
    rv.drop(f'{receiver}.pc.reader.{tilenum}.sessiontime', axis=1, inplace=True)
    return rv
