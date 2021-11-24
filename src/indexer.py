# Bruno Bastos 93302
# Leandro Silva 93446

import logging
import json
import math
import re
import sys
import os
import glob
import gzip
from tokenizer import Tokenizer
from utils import convert_size, get_directory_size


class Indexer:

    def __init__(self, tokenizer=Tokenizer(), positional=False, save_zip=False, rename_doc=False,
                 file_location=False, file_location_step=100,
                 block_threshold=1_000_000, merge_threshold=1_000_000, merge_chunk_size=1000,
                 block_dir="block/", merge_dir="indexer/", **ignore):

        self.positional = positional
        self.index = {}
        self.term_info = {}     # keeps the number of postings of a term
        path, _ = os.path.split(os.path.abspath(__file__))
        self.block_dir = block_dir if os.path.isabs(
            block_dir) else path + "/" + block_dir
        self.merge_dir = merge_dir if os.path.isabs(
            merge_dir) else path + "/" + merge_dir

        self.__block_cnt = 0
        self.block_threshold = block_threshold
        self.merge_threshold = merge_threshold
        self.merge_chunk_size = merge_chunk_size

        self.tokenizer = tokenizer

        self.save_zip = save_zip

        # FIXME: not sure
        self.n_doc_indexed = 0
        self.term_doc_weights = {}
        self.tf_idf_weights = {}

        self.__doc_id_cnt = 0
        self.doc_ids = {}
        self.rename_doc = rename_doc

        self.file_location = file_location
        self.file_location_step = file_location_step
        self.__post_cnt = 0

    @property
    def vocabulary_size(self):
        return len(self.term_info)

    @property
    def num_segments(self):
        return self.__block_cnt

    @property
    def disk_size(self):
        return convert_size(get_directory_size(self.merge_dir))

    @staticmethod
    def load_metadata(directory):
        """Static method that creates an Indexer object from a directory using the metadata."""

        indexer = Indexer.read_config(directory + ".metadata/config.json")
        indexer.read_term_info_memory()
        if indexer.rename_doc:
            indexer.read_doc_ids()

        return indexer

    @staticmethod
    def read_config(filename):
        """Static method that creates an Indexer object by providing a config file."""

        with open(filename, "r") as f:
            data = json.loads(f.read())

            indexer_data = data.get("indexer")
            tokenizer_data = data.get("tokenizer")

            if tokenizer_data:
                tokenizer = Tokenizer(**tokenizer_data)
            else:
                tokenizer = Tokenizer()

            if indexer_data:
                indexer = Indexer(tokenizer=tokenizer, **indexer_data)
            else:
                indexer = Indexer(tokenizer=tokenizer)

            return indexer

    @staticmethod
    def create_default_file(filename="config.json"):
        """Static method that creates a configuration file with the default configurations."""

        with open(filename, "w") as f:
            indexer = {
                "positional": False,
                "save_zip": False,
                "rename_doc": False,
                "file_location": False,
                "file_location_step": 100,
                "block_threshold": 1_000_000,
                "merge_threshold": 1_000_000,
                "merge_chunk_size": 1000,
                "block_dir": "block/",
                "merge_dir": "indexer/",
            }
            tokenizer = {
                "min_length": 3,
                "case_folding": True,
                "no_numbers": True,
                "stopwords_file": None,
                "contractions_file": None,
                "stemmer": True
            }
            data = {"indexer": indexer, "tokenizer": tokenizer}
            j = json.dump(data, f, indent=2)

    def write_block_disk(self):
        """Writes the current block to disk."""

        if not os.path.exists(self.block_dir):
            os.mkdir(self.block_dir)

        # resets the number of postings in memory
        self.__post_cnt = 0

        with open(self.block_dir + "block" + str(self.__block_cnt) + ".txt", "w+") as f:
            self.__block_cnt += 1
            if self.positional:
                # term doc1,pos1,pos2 doc2,pos1
                for term in sorted(self.index):
                    f.write(term + " " + " ".join([
                        doc + "," + ",".join(self.index[term][doc]) for doc in self.index[term]
                    ]) + "\n")
                    self.term_info.setdefault(term, [0, ''])[
                        0] += len(self.index[term])
            else:
                # term doc1 doc2
                for term in sorted(self.index):
                    f.write(term + " " + " ".join(self.index[term]) + "\n")
                    self.term_info.setdefault(term, [0, ''])[
                        0] += len(self.index[term])
            self.index = {}

    def write_indexer_config(self):
        """Saves the current configuration as metadata."""

        logging.info("Writing indexer config to disk")
        with open(self.merge_dir + ".metadata/config.json", "w") as f:

            indexer = {
                "positional": self.positional,
                "save_zip": self.save_zip,
                "rename_doc": self.rename_doc,
                "file_location": self.file_location,
                "file_location_step": self.file_location_step,
                "block_threshold": self.block_threshold,
                "merge_threshold": self.merge_threshold,
                "merge_chunk_size": self.merge_chunk_size,
                "block_dir": self.block_dir,
                "merge_dir": self.merge_dir,
            }
            tokenizer = {
                "min_length": self.tokenizer.min_length,
                "case_folding": self.tokenizer.case_folding,
                "no_numbers": self.tokenizer.no_numbers,
                "stopwords_file": self.tokenizer.stopwords_file,
                "contractions_file": self.tokenizer.contractions_file,
                "stemmer": True if self.tokenizer.stemmer else False
            }

            data = {"indexer": indexer, "tokenizer": tokenizer}
            j = json.dump(data, f, indent=2)

    def write_term_info_disk(self):
        """Saves term information as metadata."""

        logging.info("Writing # of postings for each term to disk")
        with open(self.merge_dir + ".metadata/term_info.txt", "w+") as f:

            # term posting_size file_location
            for term in sorted(self.term_info):
                f.write(term + " " + " ".join(str(i)
                                              for i in self.term_info[term]).strip() + "\n")

    def read_term_info_memory(self):
        """Reads term information from metadata."""

        logging.info("Reading # of postings for each term to memory")
        self.term_info = {}

        with open(self.merge_dir + ".metadata/term_info.txt", "r") as f:
            for line in f:
                term, *rest = line.strip().split(" ")
                self.term_info[term] = [int(i) for i in rest] + ([''] if len(rest) < 2 else [])

    def write_doc_ids(self):
        """Saves the dict containing the new ids for the documents as metadata."""

        if not self.rename_doc:
            logging.warning(
                "Doc rename is not in use. Cannot write doc ids to disk.")
            return

        with open(self.merge_dir + ".metadata/doc_ids.txt", "w") as f:
            for doc_id, doc in self.doc_ids.items():
                f.write(doc_id + " " + doc + "\n")

    def read_doc_ids(self):
        """Reads document id conversion from metadata."""

        if not self.rename_doc:
            logging.warning(
                "Doc rename is not in use. Cannot write doc ids to disk.")
            return

        self.doc_ids = {}
        with open(self.merge_dir + ".metadata/doc_ids.txt", "r") as f:
            for line in f:
                doc_id, doc = line.strip().split(" ")
                self.doc_ids[doc_id] = doc
        self.__doc_id_cnt = len(self.doc_ids)

    def read_posting_lists(self, term):
        """Reads the posting list of a term from disk."""

        # search for file
        files = glob.glob(self.merge_dir + "/*.txt*")
        term_file = None
        for f in files:
            f_terms = f.split("/")[-1].replace(".gz", "") \
                .split(".txt")[0].split(" ")
            if term >= f_terms[0] and term <= f_terms[1]:
                term_file = f
                break

        # search position on file
        if term_file != None:

            if self.file_location:
                term_location = 0
                sorted_term_info = sorted(self.term_info.keys())
                initial_term, final_term = term_file.split(
                    "/")[-1].replace(".gz", "").split(".txt")[0].split(" ")

                low = index = 0
                high = len(sorted_term_info) - 1

                while low <= high:
                    index = (high + low) // 2
                    if sorted_term_info[index] < term:
                        low = index + 1
                    elif sorted_term_info[index] > term:
                        high = index - 1
                    else:
                        break

                for i in range(self.file_location_step):
                    if self.term_info[sorted_term_info[index-i]][1]:
                        # previous term has file location
                        term_location = self.term_info[sorted_term_info[index-i]][1] + i
                        break

                with self.open_merge_file(term_file.replace(".gz", ""), "r") as f:
                    for i in range(term_location - 1):
                        f.readline()

                    while (line := f.readline()):

                        if self.positional:
                            # TODO: positions are not being used
                            term_r, *postings = line.strip().split(" ")
                            postings = [pos.split(',')[:2] for pos in postings]
                        else:
                            term_r, *postings = line.strip().split(" ")
                            postings = [pos.split(',') for pos in postings]

                        term_r, idf = term_r.split(',')

                        if term == term_r:
                            weights = [pos[1] for pos in postings]
                            postings = [pos[0] for pos in postings]
                            return idf, weights, postings
            else:
                with self.open_merge_file(term_file.replace(".gz", ""), "r") as f:
                    for line in f:
                        if self.positional:
                            term_r, *postings = f.readline().strip().split(" ")
                            postings = [pos.split(',')[:2] for pos in postings]
                        else:
                            term_r, *postings = line.strip().split(" ")
                            postings = [pos.split(',') for pos in postings]

                        term_r, idf = term_r.split(',')

                        if term_r == term:
                            weights = [pos[1] for pos in postings]
                            postings = [pos[0] for pos in postings]
                            return idf, weights, postings
        else:
            logging.error(
                "An error occured when searching for the term: " + term)
            exit(1)

    def clear_blocks(self):
        """Remove blocks folder."""

        logging.info("Removing unused blocks")
        blocks = glob.glob(self.block_dir + "block*.txt")

        for block in blocks:
            try:
                os.remove(block)
            except:
                logging.error("Error removing block files")

        os.rmdir(self.block_dir)

    def open_file_to_index(self, filename):
        """Open and return the dataset file."""

        try:
            f = open(filename, "r")
            f.readline()  # skip header
            return f
        except:
            pass

        try:
            f = gzip.open(filename, "rt")
            f.readline()  # skip header
            return f
        except gzip.BadGzipFile:
            pass

        logging.error("Could not open the provided file")
        exit(1)

    def open_merge_file(self, filename, mode="w"):
        """Open and return a index file."""
        if self.save_zip:
            f = gzip.open(filename + ".gz", mode + "t")
        else:
            f = open(filename, mode)
        return f

    def merge_block_disk(self):
        """Merge all blocks in disk."""

        if not os.path.exists(self.merge_dir):
            os.mkdir(self.merge_dir)
            os.mkdir(self.merge_dir + ".metadata/")

        # opens every block file and stores the file pointers in a list
        blocks = [open(block, "r")
                  for block in glob.glob(self.block_dir + "*")]
        terms = {}
        # keeps the last term for every block
        last_terms = [None for _ in range(len(blocks))]
        last_term = None                                    # keeps the min last term

        while blocks or terms:
            b = 0
            while b != len(blocks):
                # check if the last_term is the same as the last_term for the block
                if last_term == last_terms[b]:
                    f = blocks[b]
                    docs = f.readlines(self.merge_chunk_size)
                    # if the file ends it needs to be removed from the lists
                    if not docs:
                        f.close()
                        del blocks[b]
                        del last_terms[b]
                        continue

                    for doc in docs:
                        line = doc.strip().split(' ')
                        term, doc_lst = line[0], line[1:]
                        if True:  # self.ranking: # FIXME:
                            for i, doc_str in enumerate(doc_lst):
                                doc = doc_str.split(',', 1)[0]
                                # doc_lst[i] += ',' + self.term_doc_weights[term][doc]
                                n = len(doc)
                                doc_lst[i] = (doc_str[:n] + ',' + 
                                    str(self.term_doc_weights[term][doc]) + doc_str[n:])
                        terms.setdefault(term, set()).update(doc_lst)
                    last_terms[b] = term
                b += 1

            # last_term is only updated if the list is not empty
            last_term = min(last_terms) if last_terms else last_term

            total = 0
            sorted_terms = sorted(terms)
            for term in sorted_terms:
                if term >= last_term:
                    break
                total += len(terms[term])
                if total >= self.merge_threshold:
                    break

            if total >= self.merge_threshold:
                # writes the terms to the file when the terms do not go pass a threshold
                with self.open_merge_file(self.merge_dir + sorted_terms[0] + " " + term + ".txt") as f:
                    for ti, t in enumerate(sorted_terms):
                        if t <= term:
                            f.write(
                                t + "," + str(self.tf_idf_weights[t]) + " " + " ".join(sorted(terms[t])) + "\n")
                            if self.file_location and ti % self.file_location_step == 0:
                                self.term_info[t][1] = ti + 1
                            del terms[t]
            elif not blocks:
                # this will write the terms left in the last block
                with self.open_merge_file(self.merge_dir + sorted_terms[0] + " " + term + ".txt") as f:
                    for ti, t in enumerate(sorted_terms):
                        f.write(
                            t + "," + str(self.tf_idf_weights[t]) + " " + " ".join(sorted(terms[t])) + "\n")
                        if self.file_location and ti % self.file_location_step == 0:
                            self.term_info[t][1] = ti + 1
                        del terms[t]

        self.clear_blocks()

    def index_terms(self, terms, doc):
        """
        Index a list of terms provided by the tokenizer.

        @param terms: the list of terms
        @param doc: the document ID
        """
        # indexes a list of terms provided by the tokenizer

        if self.rename_doc:
            doc_id = str(self.__doc_id_cnt)
            self.doc_ids[doc_id] = doc
            doc = doc_id
            self.__doc_id_cnt += 1

        # the last indexes need to be written to a block is not full
        if self.__post_cnt >= self.block_threshold:
            logging.info("Writing to disk")
            self.write_block_disk()

        # terms -> List[Tuple(term, pos)]
        for term, pos in terms:
            if self.positional:
                # index -> Dict[term: Dict[doc: List[pos]]]
                self.index.setdefault(term, {doc: []}) \
                    .setdefault(doc, []) \
                    .append(pos)
            else:
                # index -> Dict[term: List[doc]]
                self.index.setdefault(term, [])
                self.index[term].append(doc)
        self.__post_cnt += len(terms)

    def index_file(self, filename):
        """
        Create the indexer for a dataset.

        @param filename: the dataset filename
        """
        with self.open_file_to_index(filename) as f:
            while f:
                line = f.readline()

                if len(line) == 0:
                    self.write_block_disk()
                    break
                terms, doc = self.tokenizer.tokenize(line)

                if not terms:
                    continue
                # this stores the tf-score for each term in each doc
                # term -> {doc: w}

                """
                lnc.ltc

                l uses the logarithm to calculate the term frequency
                n when calculating the weights for the document it is not necessary to 
                    use idf 
                c uses the cossine normalization which is equal to the sqrt of the sum of the squares
                    for each weight in a document
                """
                # here its done the l where the frequency of a term in this document is obtained
                temp = [term for term, pos in terms]
                cos_norm = 0
                for term in set(temp):
                    self.term_doc_weights.setdefault(term, {})
                    self.term_doc_weights[term][doc] = 1 + \
                        math.log10(temp.count(term))
                    cos_norm += self.term_doc_weights[term][doc]**2

                # here its done the cossine normalization where the previous obtained weights
                cos_norm = 1 / math.sqrt(cos_norm)
                for term in set(temp):
                    self.term_doc_weights[term][doc] *= cos_norm

                self.index_terms(terms, doc)
                self.n_doc_indexed += 1
            self.idf_score()
            self.merge_block_disk()
            self.write_term_info_disk()
            if self.rename_doc:
                self.write_doc_ids()
            self.write_indexer_config()

    def idf_score(self):

        # FIXME:
        # this can only be calculated after the file is fully indexed
        self.n_doc_indexed = sum(
            [v[0] for v in self.term_info.values()])  # ta mal

        for term in self.term_doc_weights:
            term_frequency = self.term_info[term][0]
            idf = math.log10(self.n_doc_indexed / term_frequency)
            self.tf_idf_weights[term] = idf
