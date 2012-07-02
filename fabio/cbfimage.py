#!/usr/bin/env python
# coding: utf8
"""
Authors: Jérôme Kieffer, ESRF
         email:jerome.kieffer@esrf.fr

Cif Binary Files images are 2D images written by the Pilatus detector and others.
They use a modified (simplified) byte-offset algorithm.

CIF is a library for manipulating Crystallographic information files and tries
to conform to the specification of the IUCR
"""
__author__ = "Jérôme Kieffer"
__contact__ = "jerome.kieffer@esrf.eu"
__license__ = "GPLv3+"
__copyright__ = "European Synchrotron Radiation Facility, Grenoble, France"
__version__ = ["Generated by CIF.py: Jan 2005 - April 2012",
              "Written by Jerome Kieffer: Jerome.Kieffer@esrf.eu",
              "On-line data analysis / ISDD ", "ESRF Grenoble (France)"]


import os, logging
logger = logging.getLogger("cbfimage")
import numpy
from fabioimage import fabioimage
from compression import decByteOffet_numpy, md5sum, compByteOffet_numpy
#import time

DATA_TYPES = { "signed 8-bit integer"   : numpy.int8,
               "signed 16-bit integer"  : numpy.int16,
               "signed 32-bit integer"  : numpy.int32,
               "signed 64-bit integer"  : numpy.int64
                }

MINIMUM_KEYS = ["X-Binary-Size-Fastest-Dimension",
                'ByteOrder',
                'Data type',
                'X dimension',
                'Y dimension',
                'Number of readouts']


STARTER = "\x0c\x1a\x04\xd5"
PADDING = 512

class cbfimage(fabioimage):
    """
    Read the Cif Binary File data format
    """
    def __init__(self, data=None , header=None, fname=None):
        """
        Constructor of the class CIF Binary File reader.

        @param _strFilename: the name of the file to open
        @type  _strFilename: string
        """
        fabioimage.__init__(self, data, header)
        self.cif = CIF()
        if fname is not None: #load the file)
            self.read(fname)

    @staticmethod
    def checkData(data=None):
        if data is None:
            return None
        elif numpy.issubdtype(data.dtype, int):
            return data
        else:
            return data.astype(int)


    def _readheader(self, inStream):
        """
        Read in a header in some CBF format from a string representing binary stuff

        @param inStream: file containing the Cif Binary part.
        @type inStream: opened file.
        """
        self.cif.loadCIF(inStream, _bKeepComment=True)

#        backport contents of the CIF data to the headers
        for key in self.cif:
            if key != "_array_data.data":
                self.header_keys.append(key)
                self.header[key] = self.cif[key].strip(" \"\n\r\t")

        if not "_array_data.data" in self.cif:
            raise Exception("cbfimage: CBF file %s is corrupt, cannot find data block with '_array_data.data' key" % self.fname)

        inStream2 = self.cif["_array_data.data"]
        sep = "\r\n"
        iSepPos = inStream2.find(sep)
        if iSepPos < 0 or iSepPos > 80:
            sep = "\n" #switch back to unix representation

        lines = inStream2.split(sep)
        for oneLine in lines[1:]:
            if len(oneLine) < 10:
                break
            try:
                key, val = oneLine.split(':' , 1)
            except ValueError:
                key, val = oneLine.split('=' , 1)
            key = key.strip()
            self.header_keys.append(key)
            self.header[key] = val.strip(" \"\n\r\t")
        missing = []
        for item in MINIMUM_KEYS:
            if item not in self.header_keys:
                missing.append(item)
        if len(missing) > 0:
            logger.debug("CBF file misses the keys " + " ".join(missing))


    def read(self, fname, frame=None):
        """
        Read in header into self.header and
            the data   into self.data
        """
        self.filename = fname
        self.header = {}
        self.resetvals()

        infile = self._open(fname, "rb")
        self._readheader(infile)
        # Compute image size
        try:
            self.dim1 = int(self.header['X-Binary-Size-Fastest-Dimension'])
            self.dim2 = int(self.header['X-Binary-Size-Second-Dimension'])
        except:
            raise Exception(IOError, "CBF file %s is corrupt, no dimensions in it" % fname)
        try:
            bytecode = DATA_TYPES[self.header['X-Binary-Element-Type']]
            self.bpp = len(numpy.array(0, bytecode).tostring())
        except KeyError:
            bytecode = numpy.int32
            self.bpp = 32
            logger.warning("Defaulting type to int32")
        if self.header["conversions"] == "x-CBF_BYTE_OFFSET":
            self.data = self._readbinary_byte_offset(self.cif["_array_data.data"]).astype(bytecode).reshape((self.dim2, self.dim1))
        else:
            raise Exception(IOError, "Compression scheme not yet supported, please contact FABIO development team")

        self.bytecode = self.data.dtype.type
        self.resetvals()
#        # ensure the PIL image is reset
        self.pilimage = None
        return self



    def _readbinary_byte_offset(self, inStream):
        """
        Read in a binary part of an x-CBF_BYTE_OFFSET compressed image

        @param inStream: the binary image (without any CIF decorators)
        @type inStream: python string.
        @return: a linear numpy array without shape and dtype set
        @rtype: numpy array
        """
        startPos = inStream.find(STARTER) + 4
        data = inStream[ startPos: startPos + int(self.header["X-Binary-Size"])]
        try:
            import byte_offset
        except ImportError:
            logger.warning("Error in byte_offset part: Falling back to Numpy implementation")
            myData = decByteOffet_numpy(data, size=self.dim1 * self.dim2)
        else:
            myData = byte_offset.analyseCython(data, size=self.dim1 * self.dim2)

        assert len(myData) == self.dim1 * self.dim2
        return myData


    def write(self, fname):
        """
        write the file in CBF format
        @param fname: name of the file
        @type: string
        """
        if self.data is not None:
            self.dim2, self.dim1 = self.data.shape
        else:
            raise RuntimeError("CBF image contains no data")
        binary_blob = compByteOffet_numpy(self.data)
#        l = len(binary_blob)
#        if (l % PADDING) != 0:
#            rem = PADDING - (l % PADDING)
#            binary_blob += "\x00" * rem
        dtype = "Unknown"
        for key, value in DATA_TYPES.iteritems():
            if value == self.data.dtype:
                dtype = key
        binary_block = [
                        "--CIF-BINARY-FORMAT-SECTION--",
                        "Content-Type: application/octet-stream;",
                        '     conversions="x-CBF_BYTE_OFFSET"',
                        'Content-Transfer-Encoding: BINARY',
                        "X-Binary-Size: %d" % (len(binary_blob)),
                        "X-Binary-ID: 1",
                        'X-Binary-Element-Type: "%s"' % (dtype),
                        "X-Binary-Element-Byte-Order: LITTLE_ENDIAN" ,
                        "Content-MD5: %s" % md5sum(binary_blob),
                        "X-Binary-Number-of-Elements: %s" % (self.dim1 * self.dim2),
                        "X-Binary-Size-Fastest-Dimension: %d" % self.dim1,
                        "X-Binary-Size-Second-Dimension: %d" % self.dim2,
                        "X-Binary-Size-Padding: %d" % 1,
                        "",
                        STARTER + binary_blob,
                        "",
                        "--CIF-BINARY-FORMAT-SECTION----"
                        ]

        if "_array_data.header_contents" not in self.header:
            nonCifHeaders = []
        else:
            nonCifHeaders = [i.strip()[2:] for i in self.header["_array_data.header_contents"].split("\n") if i.find("# ") >= 0]

        for key in self.header:
            if (key not in self.header_keys):
                self.header_keys.append(key)
        for key in self.header_keys:
            if key.startswith("_") :
                if key not in self.cif or self.cif[key] != self.header[key]:
                    self.cif[key] = self.header[key]
            elif key.startswith("X-Binary-"):
                pass
            elif key.startswith("Content-"):
                pass
            elif key.startswith("conversions"):
                pass
            elif key.startswith("filename"):
                pass
            elif key in self.header:
                nonCifHeaders.append("%s %s" % (key, self.header[key]))
        if len(nonCifHeaders) > 0:
            self.cif["_array_data.header_contents"] = "\r\n".join(["# %s" % i for i in nonCifHeaders])

        self.cif["_array_data.data"] = "\r\n".join(binary_block)
        self.cif.saveCIF(fname, linesep="\r\n", binary=True)

################################################################################
# CIF class
################################################################################
class CIF(dict):
    """
    This is the CIF class, it represents the CIF dictionary;
    and as a a python dictionary thus inherits from the dict built in class.
    """
    EOL = ["\r", "\n", "\r\n", "\n\r"]
    BLANK = [" ", "\t"] + EOL
    START_COMMENT = ["\"", "\'"]
    BINARY_MARKER = "--CIF-BINARY-FORMAT-SECTION--"

    def __init__(self, _strFilename=None):
        """
        Constructor of the class.

        @param _strFilename: the name of the file to open
        @type  _strFilename: filename (str) or file object
        """
        dict.__init__(self)
        self._ordered = []
        if _strFilename is not None: #load the file)
            self.loadCIF(_strFilename)

    def __setitem__(self, key, value):
        if key not in self._ordered:
            self._ordered.append(key)
        return dict.__setitem__(self, key, value)

    def pop(self, key):
        if key  in self._ordered:
            self._ordered.remove(key)
        return dict.pop(self, key)

    def popitem(self, key):
        if key  in self._ordered:
            self._ordered.remove(key)
        return dict.popitem(self, key)


    def loadCIF(self, _strFilename, _bKeepComment=False):
        """Load the CIF file and populates the CIF dictionary into the object
        @param _strFilename: the name of the file to open
        @type  _strFilename: string
        @param _strFilename: the name of the file to open
        @type  _strFilename: string
        @return: None
        """

        if isinstance(_strFilename, (str, unicode)):
            if os.path.isfile(_strFilename):
                infile = open(_strFilename, "rb")
            else:
                raise RuntimeError("CIF.loadCIF: No such file to open: %s" % _strFilename)
        #elif isinstance(_strFilename, file, bz2.BZ2File, ):
        elif "read" in dir(_strFilename):
            infile = _strFilename
        else:
            raise RuntimeError("CIF.loadCIF: what is %s type %s" % (_strFilename, type(_strFilename)))
        if _bKeepComment:
            self._parseCIF(infile.read())
        else:
            self._parseCIF(CIF._readCIF(infile))
    readCIF = loadCIF

    @staticmethod
    def isAscii(_strIn):
        """
        Check if all characters in a string are ascii,

        @param _strIn: input string
        @type _strIn: python string
        @return: boolean
        @rtype: boolean
        """
        bIsAcii = True
        for i in _strIn:
            if ord(i) > 127:
                bIsAcii = False
                break
        return bIsAcii


    @staticmethod
    def _readCIF(_instream):
        """
        - Check if the filename containing the CIF data exists
        - read the cif file
        - removes the comments

        @param _instream: the file containing the CIF data
        @type _instream: open file in read mode
        @return: a string containing the raw data
        @rtype: string
        """
        if not "readlines" in dir(_instream):
            raise RuntimeError("CIF._readCIF(instream): I expected instream to be an opened file,\
             here I got %s type %s" % (_instream, type(_instream)))
        lLinesRead = _instream.readlines()
        sText = ""
        for sLine in lLinesRead:
            iPos = sLine.find("#")
            if iPos >= 0:
                if CIF.isAscii(sLine):
                    sText += sLine[:iPos] + os.linesep

                if iPos > 80 :
                    logger.warning("This line is too long and could cause problems in PreQuest: %s", sLine)
            else :
                sText += sLine
                if len(sLine.strip()) > 80 :
                    logger.warning("This line is too long and could cause problems in PreQues: %s", sLine)
        return sText


    def _parseCIF(self, sText):
        """
        - Parses the text of a CIF file
        - Cut it in fields
        - Find all the loops and process
        - Find all the keys and values

        @param sText: the content of the CIF - file
        @type sText: string
        @return: Nothing, the data are incorporated at the CIF object dictionary
        @rtype: None
        """
        loopidx = []
        looplen = []
        loop = []
        #first of all : separate the cif file in fields
        lFields = CIF._splitCIF(sText.strip())
        #Then : look for loops
        for i in range(len(lFields)):
            if lFields[i].lower() == "loop_":
                loopidx.append(i)
        if len(loopidx) > 0:
            for i in loopidx:
                loopone, length, keys = CIF._analyseOneLoop(lFields, i)
                loop.append([keys, loopone])
                looplen.append(length)


            for i in range(len(loopidx) - 1, -1, -1):
                f1 = lFields[:loopidx[i]] + lFields[loopidx[i] + looplen[i]:]
                lFields = f1

            self["loop_"] = loop

        for i in range(len(lFields) - 1):
    #        print lFields[i], lFields[i+1]
            if len(lFields[i + 1]) == 0 : lFields[i + 1] = "?"
            if lFields[i][0] == "_" and lFields[i + 1][0] != "_":
                self[lFields[i]] = lFields[i + 1]

    @staticmethod
    def _splitCIF(sText):
        """
        Separate the text in fields as defined in the CIF

        @param sText: the content of the CIF - file
        @type sText: string
        @return: list of all the fields of the CIF
        @rtype: list
        """
        lFields = []
        while True:
            if len(sText) == 0:
                break
            elif sText[0] == "'":
                idx = 0
                bFinished = False
                while not  bFinished:
                    idx += 1 + sText[idx + 1:].find("'")
    ##########debuging    in case we arrive at the end of the text
                    if idx >= len(sText) - 1:
    #                    print sText,idx,len(sText)
                        lFields.append(sText[1:-1].strip())
                        sText = ""
                        bFinished = True
                        break

                    if sText[idx + 1] in CIF.BLANK:
                        lFields.append(sText[1:idx].strip())
                        sText1 = sText[idx + 1:]
                        sText = sText1.strip()
                        bFinished = True

            elif sText[0] == '"':
                idx = 0
                bFinished = False
                while not  bFinished:
                    idx += 1 + sText[idx + 1:].find('"')
    ##########debuging    in case we arrive at the end of the text
                    if idx >= len(sText) - 1:
    #                    print sText,idx,len(sText)
                        lFields.append(sText[1:-1].strip())
#                        print lFields[-1]
                        sText = ""
                        bFinished = True
                        break

                    if sText[idx + 1] in CIF.BLANK:
                        lFields.append(sText[1:idx].strip())
#                        print lFields[-1]
                        sText1 = sText[idx + 1:]
                        sText = sText1.strip()
                        bFinished = True
            elif sText[0] == ';':
                if sText[1:].strip().find(CIF.BINARY_MARKER) == 0:
                    idx = sText[32:].find(CIF.BINARY_MARKER)
                    if idx == -1:
                        idx = 0
                    else:
                        idx += 32 + len(CIF.BINARY_MARKER)
                else:
                    idx = 0
                bFinished = False
                while not  bFinished:
                    idx += 1 + sText[idx + 1:].find(';')
                    if sText[idx - 1] in CIF.EOL:
                        lFields.append(sText[1:idx - 1].strip())
                        sText1 = sText[idx + 1:]
                        sText = sText1.strip()
                        bFinished = True
            else:
                f = sText.split(None, 1)[0]
                lFields.append(f)
#                print lFields[-1]
                sText1 = sText[len(f):].strip()
                sText = sText1
        return lFields


    @staticmethod
    def _analyseOneLoop(lFields, iStart):
        """Processes one loop in the data extraction of the CIF file
        @param lFields: list of all the words contained in the cif file
        @type lFields: list
        @param iStart: the starting index corresponding to the "loop_" key
        @type iStart: integer
        @return: the list of loop dictionaries, the length of the data
            extracted from the lFields and the list of all the keys of the loop.
        @rtype: tuple
        """
    #    in earch loop we first search the length of the loop
    #    print lFields
#        curloop = {}
        loop = []
        keys = []
        i = iStart + 1
        bFinished = False
        while not bFinished:
            if lFields[i][0] == "_":
                keys.append(lFields[i])#.lower())
                i += 1
            else:
                bFinished = True
        data = []
        while True:
            if i >= len(lFields):
                break
            elif len(lFields[i]) == 0:
                break
            elif lFields[i][0] == "_":
                break
            elif lFields[i] in ["loop_", "stop_", "global_", "data_", "save_"]:
                break
            else:
                data.append(lFields[i])
                i += 1
        #print len(keys), len(data)
        k = 0

        if len(data) < len(keys):
            element = {}
            for j in keys:
                if k < len(data):
                    element[j] = data[k]
                else :
                    element[j] = "?"
                k += 1
            #print element
            loop.append(element)

        else:
            #print data
            #print keys
            for i in range(len(data) / len(keys)):
                element = {}
                for j in keys:
                    element[j] = data[k]
                    k += 1
    #            print element
                loop.append(element)
    #    print loop
        return loop, 1 + len(keys) + len(data), keys






#############################################################################################
########     everything needed to  write a cif file #########################################
#############################################################################################

    def saveCIF(self, _strFilename="test.cif", linesep=os.linesep, binary=False):
        """Transforms the CIF object in string then write it into the given file
        @param _strFilename: the of the file to be written
        @param linesep: line separation used (to force compatibility with windows/unix)
        @param binary: Shall we write the data as binary (True only for imageCIF/CBF)
        @type param: string
        """
        if binary:
            mode = "wb"
        else:
            mode = "w"
        try:
            fFile = open(_strFilename, mode)
        except IOError:
            print("Error during the opening of file for write: %s" %
                                                            _strFilename)
            return
        fFile.write(self.tostring(_strFilename, linesep))
        try:
            fFile.close()
        except IOError:
            print("Error during the closing of file for write: %s" %
                                                             _strFilename)


    def tostring(self, _strFilename=None, linesep=os.linesep):
        """converts a cif dictionnary to a string according to the CIF syntax
        @param _strFilename: the name of the filename to be appended in the
                                header of the CIF file
        @type _strFilename: string
        @return : a sting that corresponds to the content of the CIF - file.
        @rtype: string
        """
#        sCifText = ""
        lstStrCif = ["# " + i for i in __version__]
        if "_chemical_name_common" in self:
            t = self["_chemical_name_common"].split()[0]
        elif _strFilename is not None:
            t = os.path.splitext(os.path.split(str(_strFilename).strip())[1])[0]
        else:
            t = ""
        lstStrCif.append("data_%s" % (t))
        #first of all get all the keys :
        lKeys = self.keys()
        lKeys.sort()
        for key in lKeys[:]:
            if key in self._ordered:
                lKeys.remove(key)
        self._ordered += lKeys

        for sKey in self._ordered:
            if sKey == "loop_":
                continue
            if sKey not in self:
                self._ordered.remove(sKey)
                logger.debug("Skipping key %s from ordered list as no more present in dict")
                continue
            sValue = str(self[sKey])
            if sValue.find("\n") > -1: #should add value  between ;;
                lLine = [sKey, ";", sValue, ";", ""]
            elif len(sValue.split()) > 1: #should add value between ''
                sLine = "%s        '%s'" % (sKey, sValue)
                if len(sLine) > 80:
                    lLine = [str(sKey), sValue]
                else:
                    lLine = [sLine]
            else:
                sLine = "%s        %s" % (sKey, sValue)
                if len(sLine) > 80:
                    lLine = [str(sKey), sValue]
                else:
                    lLine = [sLine]
            lstStrCif += lLine
        if self.has_key("loop_"):
            for loop in self["loop_"]:
                lstStrCif.append("loop_ ")
                lKeys = loop[0]
                llData = loop[1]
                lstStrCif += [" %s" % (sKey) for sKey in lKeys]
                for lData in llData:
                    sLine = " "
                    for key in lKeys:
                        sRawValue = lData[key]
                        if sRawValue.find("\n") > -1: #should add value  between ;;
                            lstStrCif += [sLine, ";", str(sRawValue), ";"]
                            sLine = " "
                        else:
                            if len(sRawValue.split()) > 1: #should add value between ''
                                value = "'%s'" % (sRawValue)
                            else:
                                value = str(sRawValue)
                            if len(sLine) + len(value) > 78:
                                lstStrCif += [sLine]
                                sLine = " " + value
                            else:
                                sLine += " " + value
                    lstStrCif.append(sLine)
                lstStrCif.append("")
        return linesep.join(lstStrCif)


    def exists(self, sKey):
        """
        Check if the key exists in the CIF and is non empty.
        @param sKey: CIF key
        @type sKey: string
        @param cif: CIF dictionary
        @return: True if the key exists in the CIF dictionary and is non empty
        @rtype: boolean
        """
        bExists = False
        if self.has_key(sKey):
            if len(self[sKey]) >= 1:
                if self[sKey][0] not in ["?", "."]:
                    bExists = True
        return bExists


    def existsInLoop(self, sKey):
        """
        Check if the key exists in the CIF dictionary.
        @param sKey: CIF key
        @type sKey: string
        @param cif: CIF dictionary
        @return: True if the key exists in the CIF dictionary and is non empty
        @rtype: boolean
        """
        if not self.exists("loop_"):
            return False
        bExists = False
        if not bExists:
            for i in self["loop_"]:
                for j in i[0]:
                    if j == sKey:
                        bExists = True
        return bExists


    def loadCHIPLOT(self, _strFilename):
        """
        Load the powder diffraction CHIPLOT file and returns the
        pd_CIF dictionary in the object

        @param _strFilename: the name of the file to open
        @type  _strFilename: string
        @return: the CIF object corresponding to the powder diffraction
        @rtype: dictionary
        """
        if not os.path.isfile(_strFilename):
            print "I cannot find the file %s" % _strFilename
            raise
        lInFile = open(_strFilename, "r").readlines()
        self["_audit_creation_method"] = 'From 2-D detector using FIT2D and CIFfile'
        self["_pd_meas_scan_method"] = "fixed"
        self["_pd_spec_description"] = lInFile[0].strip()
        try:
            iLenData = int(lInFile[3])
        except ValueError:
            iLenData = None
        lOneLoop = []
        try:
            f2ThetaMin = float(lInFile[4].split()[0])
            last = ""
            for sLine in lInFile[-20:]:
                if sLine.strip() != "":
                    last = sLine.strip()
            f2ThetaMax = float(last.split()[0])
            limitsOK = True

        except (ValueError, IndexError):
            limitsOK = False
            f2ThetaMin = 180.0
            f2ThetaMax = 0
#        print "limitsOK:", limitsOK
        for sLine in lInFile[4:]:
            sCleaned = sLine.split("#")[0].strip()
            data = sCleaned.split()
            if len(data) == 2 :
                if not limitsOK:
                    f2Theta = float(data[0])
                    if f2Theta < f2ThetaMin :
                        f2ThetaMin = f2Theta
                    if f2Theta > f2ThetaMax :
                        f2ThetaMax = f2Theta
                lOneLoop.append({ "_pd_meas_intensity_total": data[1] })
        if not iLenData:
            iLenData = len(lOneLoop)
        assert (iLenData == len(lOneLoop))
        self[ "_pd_meas_2theta_range_inc" ] = "%.4f" % ((f2ThetaMax - f2ThetaMin) / (iLenData - 1))
        if self[ "_pd_meas_2theta_range_inc" ] < 0:
            self[ "_pd_meas_2theta_range_inc" ] = abs (self[ "_pd_meas_2theta_range_inc" ])
            tmp = f2ThetaMax
            f2ThetaMax = f2ThetaMin
            f2ThetaMin = tmp
        self[ "_pd_meas_2theta_range_max" ] = "%.4f" % f2ThetaMax
        self[ "_pd_meas_2theta_range_min" ] = "%.4f" % f2ThetaMin
        self[ "_pd_meas_number_of_points" ] = str(iLenData)
        self["loop_"] = [ [ ["_pd_meas_intensity_total" ], lOneLoop ] ]


    @staticmethod
    def LoopHasKey(loop, key):
        "Returns True if the key (string) exist in the array called loop"""
        try:
            loop.index(key)
            return True
        except ValueError:
            return False

