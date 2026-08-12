import re
import zipfile
import xml.etree.ElementTree as ET

MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS = {'m': MAIN, 'r': REL}


def _colonne(reference):
    lettres = re.match(r'[A-Z]+', reference).group()
    valeur = 0
    for lettre in lettres:
        valeur = valeur * 26 + ord(lettre) - 64
    return valeur


def lire_reporting(classeur):
    """Lit Reporting et Reporting N-1, quelle que soit la ligne d'entête."""
    entetes = ['Semaine', 'Date_Rapport', 'ID_Flux', 'Domaine', 'Sous_Domaine',
        'Environnement', 'Type_Livraison', 'Statut', 'Version', 'Nombre', 'Commentaire',
        'Nature_Donnée', 'Source', 'Référence_Source', 'Sprint', 'Niveau_Semaine',
        'État_Flux', 'État_Anomalie']
    donnees = []
    with zipfile.ZipFile(classeur) as archive:
        chaines = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            racine = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            chaines = [''.join(t.text or '' for t in si.findall('.//m:t', NS)) for si in racine.findall('m:si', NS)]
        livre = ET.fromstring(archive.read('xl/workbook.xml'))
        relations = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        for nom_feuille in ('Reporting', 'Reporting N-1'):
            feuille = next((f for f in livre.findall('.//m:sheet', NS) if f.attrib['name'] == nom_feuille), None)
            if feuille is None:
                continue
            relation_id = feuille.attrib['{' + REL + '}id']
            cible = next(r.attrib['Target'] for r in relations if r.attrib['Id'] == relation_id)
            chemin = cible.lstrip('/') if cible.startswith('/xl/') else 'xl/' + cible.lstrip('/')
            racine = ET.fromstring(archive.read(chemin))
            lignes = []
            for ligne in racine.findall('.//m:sheetData/m:row', NS):
                cellules = {}
                for cellule in ligne.findall('m:c', NS):
                    position = _colonne(cellule.attrib.get('r', 'A1'))
                    type_cellule = cellule.attrib.get('t')
                    valeur_xml = cellule.find('m:v', NS)
                    texte_xml = cellule.find('m:is', NS)
                    valeur = valeur_xml.text if valeur_xml is not None else ''.join(t.text or '' for t in texte_xml.findall('.//m:t', NS)) if texte_xml is not None else None
                    if type_cellule == 's' and valeur is not None:
                        valeur = chaines[int(valeur)]
                    elif type_cellule not in {'s', 'str', 'inlineStr'} and valeur is not None:
                        try:
                            valeur = float(valeur)
                            if valeur.is_integer():
                                valeur = int(valeur)
                        except ValueError:
                            pass
                    cellules[position] = valeur
                lignes.append([cellules.get(i) for i in range(1, max(cellules, default=0) + 1)])
            index_entete = next((i for i, ligne in enumerate(lignes) if 'ID_Flux' in ligne), None)
            if index_entete is None:
                continue
            entetes_feuille = lignes[index_entete]
            for ligne in lignes[index_entete + 1:]:
                valeurs = (ligne + [None] * len(entetes_feuille))[:len(entetes_feuille)]
                objet = dict(zip(entetes_feuille, valeurs))
                if objet.get('ID_Flux'):
                    donnees.append([objet.get(colonne) for colonne in entetes])
    return entetes, donnees
