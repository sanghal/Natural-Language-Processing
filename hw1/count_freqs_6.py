#! /usr/bin/python

__author__="Daniel Bauer <bauer@cs.columbia.edu> & Emily Schultz <ess2183@columbia.edu"
__date__ ="$Sep 28, 2013"

import sys
from collections import defaultdict
import math

"""
Count n-gram frequencies in a CoNLL NER data file and write counts to
stdout. 
"""

def simple_conll_corpus_iterator(corpus_file):
    """
    Get an iterator object over the corpus file. The elements of the
    iterator contain (word, ne_tag) tuples. Blank lines, indicating
    sentence boundaries return (None, None).
    """
    l = corpus_file.readline()
    while l:
        line = l.strip()
        if line: # Nonempty line
            # Extract information from line.
            # Each line has the format
            # word pos_tag phrase_tag ne_tag
            fields = line.split(" ")
            ne_tag = fields[-1]
            #phrase_tag = fields[-2] #Unused
            #pos_tag = fields[-3] #Unused
            word = " ".join(fields[:-1])
            yield word, ne_tag
        else: # Empty line
            yield (None, None)                        
        l = corpus_file.readline()

def sentence_iterator(corpus_iterator):
    """
    Return an iterator object that yields one sentence at a time.
    Sentences are represented as lists of (word, ne_tag) tuples.
    """
    current_sentence = [] #Buffer for the current sentence
    for l in corpus_iterator:        
            if l==(None, None):
                if current_sentence:  #Reached the end of a sentence
                    yield current_sentence
                    current_sentence = [] #Reset buffer
                else: # Got empty input stream
                    sys.stderr.write("WARNING: Got empty input file/stream.\n")
                    raise StopIteration
            else:
                current_sentence.append(l) #Add token to the buffer

    if current_sentence: # If the last line was blank, we're done
        yield current_sentence  #Otherwise when there is no more token
                                # in the stream return the last sentence.

def get_ngrams(sent_iterator, n):
    """
    Get a generator that returns n-grams over the entire corpus,
    respecting sentence boundaries and inserting boundary tokens.
    Sent_iterator is a generator object whose elements are lists
    of tokens.
    """
    for sent in sent_iterator:
         #Add boundary symbols to the sentence
         w_boundary = (n-1) * [(None, "*")]
         w_boundary.extend(sent)
         w_boundary.append((None, "STOP"))
         #Then extract n-grams
         ngrams = (tuple(w_boundary[i:i+n]) for i in xrange(len(w_boundary)-n+1))
         for n_gram in ngrams: #Return one n-gram at a time
            yield n_gram        


class Hmm(object):
    """
    Stores counts for n-grams and emissions. 
    """

    def __init__(self, n=3):
        assert n>=2, "Expecting n>=2."
        self.n = n
        self.emission_counts = defaultdict(int)
        self.ngram_counts = [defaultdict(int) for i in xrange(self.n)]
        self.tag_counts = defaultdict(int)
        self.all_states = set()

    def train(self, corpus_file):
        """
        Count n-gram frequencies and emission probabilities from a corpus file.
        """
        ngram_iterator = \
            get_ngrams(sentence_iterator(simple_conll_corpus_iterator(corpus_file)), self.n)

        for ngram in ngram_iterator:
            #Sanity check: n-gram we get from the corpus stream needs to have the right length
            assert len(ngram) == self.n, "ngram in stream is %i, expected %i" % (len(ngram, self.n))

            tagsonly = tuple([ne_tag for word, ne_tag in ngram]) #retrieve only the tags            
            for i in xrange(2, self.n+1): #Count NE-tag 2-grams..n-grams
                self.ngram_counts[i-1][tagsonly[-i:]] += 1
            
            if ngram[-1][0] is not None: # If this is not the last word in a sentence
                self.ngram_counts[0][tagsonly[-1:]] += 1 # count 1-gram
                self.emission_counts[ngram[-1]] += 1 # and emission frequencies

            # Need to count a single n-1-gram of sentence start symbols per sentence
            if ngram[-2][0] is None: # this is the first n-gram in a sentence
                self.ngram_counts[self.n - 2][tuple((self.n - 1) * ["*"])] += 1

        # add tag counts
        for word, ne_tag in self.emission_counts:
            self.tag_counts[ne_tag] += self.emission_counts[(word, ne_tag)]


    def write_counts(self, output, printngrams=[1,2,3]):
        """
        Writes counts to the output file object.
        Format:

        """
        # First write counts for emissions
        for word, ne_tag in self.emission_counts:            
            output.write("%i WORDTAG %s %s\n" % (self.emission_counts[(word, ne_tag)], ne_tag, word))


        # Then write counts for all ngrams
        for n in printngrams:            
            for ngram in self.ngram_counts[n-1]:
                ngramstr = " ".join(ngram)
                output.write("%i %i-GRAM %s\n" %(self.ngram_counts[n-1][ngram], n, ngramstr))

    def write_predicts(self, dev_file, output):
        """Writes to output in: (word tag log_probability) format."""
        dev_infile = file(dev_file, "r")

        for line in dev_infile:
            word = line.strip()
            if word: # Nonempty line
                if self.word_counts[word] < 5 and word.isdigit():
                    tag = self.simple_named_entity_tagger("_NUM_")
                    lprob = math.log(self.e("_NUM_", tag))
                elif self.word_counts[word] < 5 and not word.islower():
                    tag = self.simple_named_entity_tagger("_CAP_")
                    lprob = math.log(self.e("_CAP_", tag))
                elif self.word_counts[word] >= 5:
                    tag = self.simple_named_entity_tagger(word)
                    lprob = math.log(self.e(word, tag))
                else:
                    tag = self.simple_named_entity_tagger("_RARE_")
                    lprob = math.log(self.e("_RARE_", tag))
                output.write("%s %s %f\n" %(word, tag, lprob))
            else: # for matchup with eval script
                output.write("\n")

    def e(self, x, y):
        """
        Computes emission parameters
        e(x|y) = Count(y -> x)/Count(y)
        """
        if self.tag_counts[y] != 0:
            return self.emission_counts[(x, y)]/float(self.tag_counts[y])
        else:
            return 0.0 # avoid division by zero error if tag_count is zero

    def simple_named_entity_tagger(self, word_x):
        """Returns the tag y* = argmax(y) e(x|y) for every word x."""

        tag = "ERROR: NO BEST TAG FOUND" # if no tag found, uh-oh
        prob = 0.0
        for y in self.all_states:
            cur_prob = self.e(word_x, y)
            if cur_prob > prob:
                tag = y
                prob = cur_prob
        return tag

    def read_counts(self, corpusfile):

        self.n = 3
        self.emission_counts = defaultdict(int)
        self.ngram_counts = [defaultdict(int) for i in xrange(self.n)]
        self.all_states = set()
        self.all_words = set()
        self.word_counts = defaultdict(int)

        for line in corpusfile:
            parts = line.strip().split(" ")
            count = float(parts[0])
            if parts[1] == "WORDTAG":
                ne_tag = parts[2]
                word = parts[3]
                self.emission_counts[(word, ne_tag)] = count
                self.all_states.add(ne_tag)
                self.all_words.add(word)
                self.tag_counts[ne_tag] += self.emission_counts[(word, ne_tag)] 
                self.word_counts[word] += 1
            elif parts[1].endswith("GRAM"):
                n = int(parts[1].replace("-GRAM",""))
                ngram = tuple(parts[2:])
                self.ngram_counts[n-1][ngram] = count
                


def usage():
    print """
    python count_freqs.py [input_file] > [output_file]
        Read in a named entity tagged training input file and produce counts.
    """

if __name__ == "__main__":

    if len(sys.argv)!=2: # Expect exactly one argument: the training data file
        usage()
        sys.exit(2)

    try:
        input = file(sys.argv[1],"r")
    except IOError:
        sys.stderr.write("ERROR: Cannot read inputfile %s.\n" % arg)
        sys.exit(1)
    
    # Initialize a trigram counter
    counter = Hmm(3)
    # Collect counts
    counter.train(input)
    # Write the counts
    counter.write_counts(sys.stdout)