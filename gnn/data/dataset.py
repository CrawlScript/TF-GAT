# coding=utf-8

import os
import numpy as np
import re

from scipy.sparse import csr_matrix

from gnn.data.meta_network import MetaNetwork, N_TYPE_NODE, N_TYPE_LABEL


class Tokenizer(object):
    def __init__(self):
        self.token_id_index_dict = {}
        self.token_index_id_dict = {}

    # get token_index if token_id exists
    # otherwise create token_index for token_id
    def get_or_create_token_index(self, token_id):
        if token_id in self.token_id_index_dict:
            return self.token_id_index_dict[token_id]
        else:
            token_index = self.num_tokens()
            self.token_index_id_dict[token_index] = token_id
            self.token_id_index_dict[token_id] = token_index
            return token_index

    def get_token_index(self, token_id):
        return self.token_id_index_dict[token_id]

    def num_tokens(self):
        return len(self.token_id_index_dict)

    # sentence:str => words:list[str]
    def tokenize(self, s):
        raise NotImplementedError()

    def tokenize_to_indices(self, s, create_token_index=True):
        token_ids = self.tokenize(s)
        if create_token_index:
            token_indices = [self.get_or_create_token_index(token_id) for token_id in token_ids]
        else:
            token_indices = [self.get_token_index(token_id) for token_id in token_ids]
        return token_indices


# default tokenizer, splitting by white spaces
class WhiteSpaceTokenizer(Tokenizer):
    def tokenize(self, s):
        return s.split()


class EnglishWordTokenizer(Tokenizer):
    def __init__(self):
        super().__init__()
        self.punc_re = re.compile("[^a-zA-Z]")

    def tokenize(self, s):
        s = s.lower()
        s = self.punc_re.sub(" ", s)
        return s.split()


# construct dataset from a data directory
# the data directory should contain:
#   - adjedges.txt or edgelist.txt
#   - docs.txt
#   - labels.txt
class GraphDataset(MetaNetwork):
    FORMAT_ADJEDGES = "adjedges"
    FORMAT_EDGELIST = "edgelist"

    # read data from data_dir
    # if ignore_featureless_node is True, nodes without content or features will be ignored
    def __init__(self, data_dir, data_format=FORMAT_ADJEDGES, ignore_featureless_node=True, tokenizer=None):
        super().__init__()

        self.data_dir = data_dir
        self.data_format = data_format
        self.ignore_featureless_node = True

        if tokenizer is None:
            self.tokenizer = EnglishWordTokenizer()
        else:
            self.tokenizer = tokenizer

        # read document first such that nodes with content will have small index
        self._read_docs()
        self._read_labels()
        self._read_structure()

    def _read_structure(self):
        if self.data_format == GraphDataset.FORMAT_ADJEDGES:
            self._read_adjedges()
        else:
            self._read_edgelist()

    def _read_adjedges(self):
        adjedges_fpath = os.path.join(self.data_dir, "adjedges.txt")
        with open(adjedges_fpath, "r", encoding="utf-8") as f:
            for line in f:
                node_ids = line.split()
                node_id0 = node_ids[0]
                if self.ignore_featureless_node and not self.has_node_id(N_TYPE_NODE, node_id0):
                    continue
                node_index0 = self.get_or_create_node_index(N_TYPE_NODE, node_id0)
                for node_id1 in node_ids[1:]:
                    if self.ignore_featureless_node and not self.has_node_id(N_TYPE_NODE, node_id1):
                        continue
                    node_index1 = self.get_or_create_node_index(N_TYPE_NODE, node_id1)
                    if node_index0 != node_index1:
                        self.add_edges(N_TYPE_NODE, N_TYPE_NODE, node_index0, node_index1, 1.0)

    def _read_edgelist(self):
        edgelist_fpath = os.path.join(self.data_dir, "edgelist.txt")
        with open(edgelist_fpath, "r", encoding="utf-8") as f:
            for line in f:
                items = line.split()
                node_id0 = items[0]
                node_id1 = items[1]
                if len(items) == 3:
                    weight = float(items[2])
                if self.ignore_featureless_node and not self.has_node_id(N_TYPE_NODE, node_id0):
                    continue
                node_index0 = self.get_or_create_node_index(N_TYPE_NODE, node_id0)
                if self.ignore_featureless_node and not self.has_node_id(N_TYPE_NODE, node_id1):
                    continue
                node_index1 = self.get_or_create_node_index(N_TYPE_NODE, node_id1)
                if node_index0 != node_index1:
                    self.add_edges(N_TYPE_NODE, N_TYPE_NODE, node_index0, node_index1, weight)

    def _read_docs(self):
        docs_fpath = os.path.join(self.data_dir, "docs.txt")
        with open(docs_fpath, "r", encoding="utf-8") as f:
            for line in f:
                node_id, sentence = re.split(r"\s+", line, 1)
                node_index = self.get_or_create_node_index(N_TYPE_NODE, node_id)
                token_indices = self.tokenizer.tokenize_to_indices(sentence)
                self.set_node_attr(N_TYPE_NODE, node_index, "features", token_indices)

    def _read_labels(self):
        labels_fpath = os.path.join(self.data_dir, "labels.txt")
        with open(labels_fpath, "r", encoding="utf-8") as f:
            for line in f:
                node_id, label_id = line.split()
                if self.ignore_featureless_node:
                    node_index = self.get_node_index(N_TYPE_NODE, node_id)
                else:
                    node_index = self.get_or_create_node_index(N_TYPE_NODE, node_id)
                label_index = self.get_or_create_node_index(N_TYPE_LABEL, label_id)
                self.set_node_attr(N_TYPE_NODE, node_index, "label", label_index)

    def feature_matrix(self, bag_of_words=False, sparse=True):
        # if bag of words, return sparse
        if bag_of_words:
            num_nodes = self.num_nodes(N_TYPE_NODE)
            feature_dim = self.tokenizer.num_tokens()
            data = []
            row = []
            col = []
            for node_index in range(num_nodes):
                token_indices = self.get_node_attr(N_TYPE_NODE, node_index, "features")
                for token_index in token_indices:
                    data.append(1)
                    row.append(node_index)
                    col.append(token_index)
            feature_matrix = csr_matrix((data, (row, col)), shape=(num_nodes, feature_dim))
            if not sparse:
                feature_matrix = feature_matrix.todense().astype(np.float32)
            return feature_matrix

            # feature_matrix = np.zeros((num_nodes, feature_dim), dtype=np.float32)
            # for node_index in range(num_nodes):
            #     token_indices = self.get_node_attr(N_TYPE_NODE, node_index, "features")
            #     feature_matrix[node_index][token_indices] = 1.0
            # return feature_matrix

        else:
            raise NotImplementedError()

    def num_classes(self):
        return self.num_nodes(N_TYPE_LABEL)

    def label_list_or_matrix(self, one_hot=False):
        label_indices = self.get_node_attrs(N_TYPE_NODE, range(self.num_nodes(N_TYPE_NODE)), "label")
        num_nodes = self.num_nodes(N_TYPE_NODE)
        if one_hot:
            label_matrix = np.zeros((num_nodes, self.num_classes()), dtype=np.int32)
            label_matrix[np.arange(num_nodes), label_indices] = 1
            return label_matrix
        else:
            return np.array(label_indices)

    def adj_matrix(self, node_type0=N_TYPE_NODE, node_type1=N_TYPE_NODE, sparse=False):
        return super().adj_matrix(node_type0, node_type1, sparse)

    def split_train_and_test(self, node_type=N_TYPE_NODE, training_rate=0.3):
        return super().split_train_and_test(node_type, training_rate)