from nltk.stem import SnowballStemmer
import os
import re
# https://towardsdatascience.com/text-normalization-7ecc8e084e31
# https://towardsdatascience.com/text-normalization-for-natural-language-processing-nlp-70a314bfa646

class Review:
    ID = 2
    HEADLINE = 11
    BODY = 12

class Tokenizer:
    
    def __init__(self, min_length=3, case_folding=True, no_numbers=True, stopwords=True, stemmer=True):
        self.min_length = min_length
        self.case_folding = case_folding
        self.no_numbers = no_numbers
        self.stopwords = {}
        self.stemmer = None
        if stopwords:
            dirname, _ = os.path.split(os.path.abspath(__file__))
            self.stopwords = {w for w in open(dirname + "/../data/nltk_en_stopwords.txt", "r").read().split()}
        if stemmer:
            self.stemmer = SnowballStemmer("english")

    def normalize_tokens(self, terms):
        # TODO: what to do with hiphens?

        if self.min_length:
            terms = [term for term in terms if len(term) >= self.min_length]
        if self.stopwords:
            terms = [term for term in terms if term.lower() not in self.stopwords]
        if self.no_numbers:
            terms = [term for term in terms if not term.replace(",", "").replace(".", "").isdigit()]
        if self.case_folding:
            terms = [term.casefold() for term in terms]
        if self.stemmer:
            terms = [self.stemmer.stem(term) for term in terms]

        return terms

    def tokenize(self, line):
        doc = line.split('\t')
        review = doc[Review.HEADLINE] + doc[Review.BODY]
        review_id = doc[Review.ID]

        #self.update_fields(doc)
        terms = []
        for pos, term in enumerate(self.normalize_tokens(review.split())):
            terms.append((term, pos))
        # { token: { doc1: p1, p2} }
        # FIXME: change the return value
        # it is only like this to match the indexer
        return terms, review_id

#t = Tokenizer()
# ps_stem_sent = [ps.stem(words_sent) for words_sent in sent]
# print(ps_stem_sent)


