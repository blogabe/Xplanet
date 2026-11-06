"""Parse provider XML without document type or entity declarations."""
import xml.etree.ElementTree as ET
from .errors import FeedError

class NoDeclarations(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise FeedError('Provider XML contains unsupported XML declarations')

def parse(raw):
    return ET.fromstring(raw, parser=ET.XMLParser(target=NoDeclarations()))
