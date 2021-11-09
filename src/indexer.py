import re
import sys
import os
import glob
from tokenizer import Tokenizer

class Indexer:

    def __init__(self, positional=False, block_directory="./block/"):
        self.positional = positional
        self.index = {}
        self.term_posting_size = {}     # keeps the number of postings of a term
        self.block_directory = block_directory
        self.block_cnt = 0
        self.threshold = 10000         # change this value or let it be set by the user
        self.tokenizer = Tokenizer()

    def write_block_disk(self):

        if not os.path.exists(self.block_directory):
            os.mkdir(self.block_directory)

        # writes the current indexer block to disk
        with open(self.block_directory + "block" + str(self.block_cnt) + ".txt", "w+") as f:
            self.block_cnt += 1
            if self.positional:
                assert False, "Not implemented"
            else:
                
                for term in sorted(self.index.keys()):
                    f.write(term + " " + " ".join(self.index[term]) + "\n")

                self.term_posting_size[term] = len(self.index[term])
                self.index = {}

    def clear_blocks(self):
        print("Removing unused blocks")
        blocks = glob.glob("./block/block*.txt")
        
        for block in blocks:
            try:
                os.remove(block)
            except:
                print("Error removing block files")
        

    def read_term_to_memory(self, term):
        # TODO: we need to know where this term is stored
        # maybe use an index that points to a certain letter and start read from there
        with open("random.txt", "r") as f:
           pass

    def merge_block_disk(self):
    
        blocks = glob.glob(self.block_directory + "*")
        chunk_size = 1000
        threshold = 5000
        
        files = [open(block, "r") for block in blocks]
            
        terms = {}
        last_terms = [None for _ in range(len(blocks))]
        last_term = None
        while blocks:
            remove_lst = []
            for i, block in enumerate(blocks):
                
                if last_term == last_terms[i]:
                    f = files[i]
                    docs = f.readlines(chunk_size)
                    
                    if not docs:
                        remove_lst.append(i)

                    for doc in docs:
                        line = doc.strip().split(" ")
                        term = line[0]
                        doc_lst = line[1:]
                        terms.setdefault(term, []).extend(doc_lst) 
                        last_terms[i] = term

            last_term = min(last_terms)
            
            total = 0
            sorted_terms = sorted(terms.keys())
            for term in sorted_terms:
                if term >= last_term:
                    break
                total += len(terms[term])
                if total >= threshold:
                    last_term2 = term
                    break

            if total >= threshold:
                # write to file
                f = open(sorted_terms[0] + "-" + last_term + ".txt", "w+") 
                for term in sorted_terms:
                    if term <= last_term2:
                        for posting in terms[term]:
                            f.write(term + " " + str(posting) + "\n")
                        del terms[term]
                f.close()

            for i in remove_lst:    
                files[i].close()
                del files[i]
                del blocks[i]
                del last_terms[i]

        self.clear_blocks()

    def index_terms(self, terms, doc):
        # indexes a list of terms provided by the tokenizer
    
        if len(self.index.values()) >= self.threshold:
            print("Writing to disk")
            self.write_block_disk()

        # terms -> List[Tuple(term, pos)]
        # FIXME: need the positions but tokenizer is not ready yet
        #for term, pos in terms:
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
