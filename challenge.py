#!/usr/bin/env python
import json
import optparse
import os
import sys
from datetime import timedelta, datetime
from flask import Flask, render_template
from onion_py.manager import Manager
from onion_py.objects import *

app = Flask(__name__)

@app.route("/")
def hello():
  fingerprints = read_fingerprints("fingerprints.txt")
  fingerprints = ",".join(fingerprints)
  print(fingerprints)
  return render_template('index.html',relays=[fingerprints])

@app.route("/relays/<fp>")
def show_relays(fp):
  fingerprints = fp.split(",")
  manager = Manager()
  docs = [manager.query('details', lookup=f, fields=['consensus_weight_fraction','nickname']) for f in fingerprints]
  print("{} docs found".format(len(docs)))
  relays = []
  cwf_sum = 0.0
  for d in docs:
    if len(d.relays) > 0:
      relays.append([d.relays[0].nickname,d.relays[0].consensus_weight_fraction])
      cwf_sum = cwf_sum + d.relays[0].consensus_weight_fraction

  return render_template('relays.html', relays=relays, cwf=cwf_sum)



def main():
    fingerprints = read_fingerprints(options.in_fingerprints)
    download_and_combine_documents(options.out_bandwidth, 'bandwidth',
                                   fingerprints)
    download_and_combine_documents(options.out_weights, 'weights',
                                   fingerprints)
    download_and_combine_documents(options.out_clients, 'clients',
                                   fingerprints)
    download_and_combine_documents(options.out_uptime, 'uptime',
                                   fingerprints)


def read_fingerprints(fingerprints_path):
    if not os.path.exists(fingerprints_path):
        print('Fingerprints file %s does not exist.  Exiting.' % (
               fingerprints_path, ))
        sys.exit(1)
    fingerprints_file = open(fingerprints_path)
    fingerprints_content = fingerprints_file.read()
    fingerprints_file.close()
    fingerprints = []
    for line in fingerprints_content.split('\n'):
        if '#' in line:
            stripped_line = line[:line.index('#')].strip()
        else:
            stripped_line = line.strip()
        if len(stripped_line) == 40:
            fingerprints.append(stripped_line)
        elif len(stripped_line) > 0:
            print('Skipping invalid fingerprint: %s' % (stripped_line, ))
    return fingerprints

def download_and_combine_documents(out_path, resource_name, fingerprints):
    # TODO put me in after testing
    #downloads = download_documents(resource_name, fingerprints)
    downloads = read_documents_from_disk(resource_name, fingerprints)
    combined_document = combine_downloads(downloads)
    write_combined_document_to_disk(out_path, combined_document)

def download_documents(resource_name, fingerprints):
    downloads = []
    for fingerprint in fingerprints:
        request = 'https://onionoo.torproject.org/%s?lookup=%s' % (
                   resource_name, fingerprint, )
        try:
            response = urllib2.urlopen(request)
        except urllib2.HTTPError as error:
            print("Error " + str(error.code) + ": " + error.reason)
        downloads.append(response.read())
    return downloads

def read_documents_from_disk(resource_name, fingerprints):
    # TODO Take me out after testing
    downloads = []
    for fingerprint in fingerprints:
        document_path = '%s/%s' % (resource_name, fingerprint, )
        if os.path.exists(document_path):
            document_file = open(document_path)
            document_content = document_file.read()
            document_file.close()
            downloads.append(document_content)
    return downloads

def combine_downloads(downloads):
    """
    Combine an arbitrary number of downloaded Onionoo documents consisting
    of four fields:
     - relays_published (string): ignored here
     - relays (array of objects): contains zero or more documents
     - bridges_published (string): ignored here
     - bridges (array of objects): contains zero or more documents
    Return a single document with graphs containing data from all relays
    and bridges.
    """
    documents = []
    for download in downloads:
        download_dict = json.loads(download)
        documents.extend(download_dict['relays'])
        documents.extend(download_dict['bridges'])
    return combine_documents(documents)

def combine_documents(documents):
    """
    Combine one or more relay or bridge documents into a single document
    with the following fields:
     - fingerprints (array of strings)
     - (all combined graphs contained in relay or bridge documents)
    """
    fingerprints = []
    graphs = {}
    for document in documents:
        for key, value in document.items():
            if key == 'fingerprint':
                fingerprints.append(value)
            elif key in graphs:
                graphs[key].append(value)
            else:
                graphs[key] = [value]
    combined_document = {}
    combined_document['fingerprints'] = fingerprints
    for key, value in graphs.items():
        combined_document[key] = combine_graphs(value)
    return combined_document

def combine_graphs(graphs):
    """
    Combine one or more sets of graphs into a single set of graphs.
    """
    histories = {}
    for graph in graphs:
        for key, value in graph.items():
            if key in histories:
                histories[key].append(value)
            else:
                histories[key] = [value]
    combined_graph = {}
    for key, value in histories.items():
        combined_graph[key] = combine_histories(value)
    return combined_graph

def combine_histories(histories):
    """
    Combine an arbitrary number of graphs for a given time period into a
    single graph.  The combined graph will range from max(first) to
    max(last) of input graphs.
    """
    first, last, interval = [], [], []
    values = {}
    for history in histories:
        first.append(history['first'])
        last.append(history['last'])
        interval.append(history['interval'])
        factor = history['factor']
        current = datetime.strptime(history['first'], '%Y-%m-%d %H:%M:%S')
        for value in history['values']:
            if value:
                denormalized_value = value * history['factor']
                if current in values:
                    values[current].append(denormalized_value)
                else:
                    values[current] = [denormalized_value]
            current = current + timedelta(seconds=history['interval'])
    new_first = datetime.strptime(history['first'], '%Y-%m-%d %H:%M:%S')
    new_last = datetime.strptime(history['last'], '%Y-%m-%d %H:%M:%S')
    new_interval = max(interval)
    new_current = new_first
    new_denormalized_values = []
    new_max = 0
    while new_current <= new_last:
        if new_current in values:
            new_value = sum(values[new_current])
            new_denormalized_values.append(new_value)
            if new_value > new_max:
                new_max = new_value
        else:
            new_denormalized_values.append(None)
        new_current = new_current + timedelta(seconds=new_interval)
    new_factor = new_max / 999.0
    new_normalized_values = []
    for value in new_denormalized_values:
        if value:
            new_normalized_values.append(int(value / new_factor))
        else:
            new_normalized_values.append(None)
    combined_history = {}
    combined_history['first'] = max(first)
    combined_history['last'] = max(last)
    combined_history['interval'] = new_interval
    combined_history['factor'] = new_factor
    combined_history['count'] = len(new_normalized_values)
    combined_history['values'] = new_normalized_values
    return combined_history

def write_combined_document_to_disk(out_path, combined_document):
    out_file = open(out_path, 'w')
    out_file.write(json.dumps(combined_document))
    out_file.close()

if __name__ == '__main__':
    app.debug = True
    app.run()


