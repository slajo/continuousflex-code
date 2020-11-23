# **************************************************************************
# *
# * Authors:  Mohamad Harastani          (mohamad.harastani@upmc.fr)
# * TODO: Add Remi
# *
# * IMPMC, UPMC Sorbonne University
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'scipion@cnb.csic.es'
# *
# **************************************************************************


from os.path import basename

from pwem.convert.atom_struct import cifToPdb
from pyworkflow.utils import replaceBaseExt

from pyworkflow.utils import isPower2, getListFromRangeString
from pyworkflow.utils.path import copyFile, cleanPath
import pyworkflow.protocol.params as params
from pwem.protocols import ProtAnalysis3D

from pyworkflow.protocol.params import NumericRangeParam
import pwem as em
import pwem.emlib.metadata as md

from xmipp3.base import XmippMdRow
from xmipp3.convert import (writeSetOfParticles, xmippToLocation,
                            getImageLocation, createItemMatrix,
                            setXmippAttributes)
from .convert import modeToRow

NMA_ALIGNMENT_WAV = 0
NMA_ALIGNMENT_PROJ = 1

MODE_RELATION_LINEAR = 0
MODE_RELATION_3CLUSTERS = 1
MODE_RELATION_5CLUSTERS = 2

MISSINGWEDGE_YES = 0
MISSINGWEDGE_NO = 1


class FlexProtSynthesizeSubtomo(ProtAnalysis3D):
    """ Protocol for flexible angular alignment. """
    _label = 'synthesize subtomograms'

    # --------------------------- DEFINE param functions --------------------------------------------
    def _defineParams(self, form):
        form.addSection(label='Input')
        form.addParam('inputModes', params.PointerParam, pointerClass='SetOfNormalModes',
                      label="Normal modes",
                      help='Set of modes computed by normal mode analysis.')
        form.addParam('modeList', NumericRangeParam,
                      label="Modes selection",
                      help='Select the normal modes that will be used for image analysis. \n'
                           'If you leave this field empty, all computed modes will be selected for image analysis.\n'
                           'You have several ways to specify the modes.\n'
                           '   Examples:\n'
                           ' "7,8-10" -> [7,8,9,10]\n'
                           ' "8, 10, 12" -> [8,10,12]\n'
                           ' "8 9, 10-12" -> [8,9,10,11,12])\n')
        form.addParam('modeRelationChoice', params.EnumParam, default=MODE_RELATION_LINEAR,
                      choices=['Linear relationship', 'Clusters (3 clusters)', 'Clusters (5 clusters)'],
                      label='Relationship between the modes',
                      help='TODO')
        # TODO: volumes size, sampling rate, number of volumes

        # form.addParam('copyDeformations', params.PathParam,
        #               expertLevel=params.LEVEL_ADVANCED,
        #               label='Precomputed results (for development)',
        #               help='Only for tests during development. Enter a metadata file with precomputed elastic '
        #                    'and rigid-body alignment parameters and perform '
        #                    'all remaining steps using this file.')
        #
        form.addSection(label='Missing wedge parameters')
        form.addParam('modeRelationChoice', params.EnumParam, default=MISSINGWEDGE_YES,
                      choices=['Simulate missing wedge artefacts', 'No missing wedge'],
                      label='Missing Wedge choice',
                      help='TODO')
        form.addParam('tiltStep', params.IntParam, default=1,
                      label='tilt step angle',
                      help='later')
        form.addParam('tiltLow', params.IntParam, default=-60,
                      condition='modeRelationChoice==%d' % MISSINGWEDGE_YES,
                      label='Lower tilt value',
                      help='The lower tilt angle used in obtaining the tilt series')
        form.addParam('tiltHigh', params.IntParam, default=60,
                      condition='modeRelationChoice==%d' % MISSINGWEDGE_YES,
                      label='Upper tilt value',
                      help='The upper tilt angle used in obtaining the tilt series')
        form.addSection(label='Noise and CTF')
        # Add the choice of SNR that will be add to the images
        # Add the parameters for the CTF
        # XMIPP_STAR_1 *
        # #
        # data_noname
        # _ctfVoltage 200
        # _ctfSphericalAberration 2
        # _ctfSamplingRate 2.2
        # _magnification
        # 50000
        # _ctfDefocusU - 10000.0
        # _ctfDefocusV - 10000.0
        # _ctfQ0 - 0.112762
        form.addSection('reconstruction')
        # TODO: add am option to choose beterrn wbp and fourier reconstruction
        # form.addParam('discreteAngularSampling', params.FloatParam, default=10,
        #               label="Discrete angular sampling (deg)",
        #               help='This is the angular step (in degrees) with which a library of reference projections '
        #                    'is computed for rigid-body alignment in Projection Matching and Wavelets methods. \n'
        #                    'This alignment is refined with Splines method when Wavelets and Splines alignment is chosen.')

        form.addSection('rigid body alignment')
        # TODO: add an option to generate with/without rotations and give a limit to the shift value

        form.addParallelSection(threads=0, mpi=8)

        # --------------------------- INSERT steps functions --------------------------------------------

    def getInputPdb(self):
        """ Return the Pdb object associated with the normal modes. """
        return self.inputModes.get().getPdb()

    def _insertAllSteps(self):
        self._insertFunctionStep("generate_deformations")

        # atomsFn = self.getInputPdb().getFileName()
        # # Define some outputs filenames
        # self.imgsFn = self._getExtraPath('images.xmd')
        # self.modesFn = self._getExtraPath('modes.xmd')
        # self.structureEM = self.inputModes.get().getPdb().getPseudoAtoms()
        # if self.structureEM:
        #     self.atomsFn = self._getExtraPath(basename(atomsFn))
        #     copyFile(atomsFn, self.atomsFn)
        # else:
        #     localFn = self._getExtraPath(replaceBaseExt(basename(atomsFn), 'pdb'))
        #     cifToPdb(atomsFn, localFn)
        #     self.atomsFn = self._getExtraPath(basename(localFn))
        #
        # self._insertFunctionStep('convertInputStep', atomsFn)
        #
        # if self.copyDeformations.empty():  # ONLY FOR DEBUGGING
        #     self._insertFunctionStep("performNmaStep", self.atomsFn, self.modesFn)
        # else:
        #     # TODO: for debugging and testing it will be useful to copy the deformations
        #     # metadata file, not just the deformation.txt file
        #     self._insertFunctionStep('copyDeformationsStep', self.copyDeformations.get())
        #
        # self._insertFunctionStep('createOutputStep')

    # --------------------------- STEPS functions --------------------------------------------
    def convertInputStep(self, atomsFn):
        pass
        # Write the modes metadata taking into account the selection
        # self.writeModesMetaData()
        # Write a metadata with the normal modes information
        # to launch the nma alignment programs
        # writeSetOfParticles(self.inputParticles.get(), self.imgsFn)

    # This is now done differently (see _insertAllSteps) and this line must be removed now
    # Copy the atoms file to current working dir
    # copyFile(atomsFn, self.atomsFn)

    def generate_deformations(self):
        # use the input relationship between the modes to generate normal mode amplitudes metadata
        pass


    def writeModesMetaData(self):
        """ Iterate over the input SetOfNormalModes and write
        the proper Xmipp metadata.
        Take into account a possible selection of modes (This option is 
        just a shortcut for testing. The recommended
        way is just create a subset from the GUI and use that as input)
        """
        # modeSelection = []
        # if self.modeList.empty():
        #     modeSelection = []
        # else:
        #     modeSelection = getListFromRangeString(self.modeList.get())
        #
        # mdModes = md.MetaData()
        #
        # inputModes = self.inputModes.get()
        # for mode in inputModes:
        #     # If there is a mode selection, only
        #     # take into account those selected
        #     if not modeSelection or mode.getObjId() in modeSelection:
        #         row = XmippMdRow()
        #         modeToRow(mode, row)
        #         row.writeToMd(mdModes, mdModes.addObject())
        # mdModes.write(self.modesFn)
        pass

    def copyDeformationsStep(self, deformationMd):
        pass
        # copyFile(deformationMd, self.imgsFn)
        # # We need to update the image name with the good ones
        # # and the same with the ids.
        # inputSet = self.inputParticles.get()
        # mdImgs = md.MetaData(self.imgsFn)
        # for objId in mdImgs:
        #     imgPath = mdImgs.getValue(md.MDL_IMAGE, objId)
        #     index, fn = xmippToLocation(imgPath)
        #     # Conside the index is the id in the input set
        #     particle = inputSet[index]
        #     mdImgs.setValue(md.MDL_IMAGE, getImageLocation(particle), objId)
        #     mdImgs.setValue(md.MDL_ITEM_ID, int(particle.getObjId()), objId)
        # mdImgs.write(self.imgsFn)

    def performNmaStep(self, atomsFn, modesFn):
        pass
        # sampling = self.inputParticles.get().getSamplingRate()
        # discreteAngularSampling = self.discreteAngularSampling.get()
        # trustRegionScale = self.trustRegionScale.get()
        # odir = self._getTmpPath()
        # imgFn = self.imgsFn
        #
        # args = "-i %(imgFn)s --pdb %(atomsFn)s --modes %(modesFn)s --sampling_rate %(sampling)f "
        # args += "--discrAngStep %(discreteAngularSampling)f --odir %(odir)s --centerPDB "
        # args += "--trustradius_scale %(trustRegionScale)d --resume "
        #
        # if self.getInputPdb().getPseudoAtoms():
        #     args += "--fixed_Gaussian "
        #
        # if self.alignmentMethod == NMA_ALIGNMENT_PROJ:
        #     args += "--projMatch "
        #
        # self.runJob("xmipp_nma_alignment", args % locals())
        #
        # cleanPath(self._getPath('nmaTodo.xmd'))
        #
        # inputSet = self.inputParticles.get()
        # mdImgs = md.MetaData(self.imgsFn)
        # for objId in mdImgs:
        #     imgPath = mdImgs.getValue(md.MDL_IMAGE, objId)
        #     index, fn = xmippToLocation(imgPath)
        #     # Conside the index is the id in the input set
        #     particle = inputSet[index]
        #     mdImgs.setValue(md.MDL_IMAGE, getImageLocation(particle), objId)
        #     mdImgs.setValue(md.MDL_ITEM_ID, int(particle.getObjId()), objId)
        # mdImgs.write(self.imgsFn)

    def createOutputStep(self):
        pass


    # --------------------------- INFO functions --------------------------------------------
    def _summary(self):
        summary = []
        return summary

    def _validate(self):
        errors = []
        # xdim = self.inputParticles.get().getDim()[0]
        # if not isPower2(xdim):
        #     errors.append("Image dimension (%s) is not a power of two, consider resize them" % xdim)
        return errors

    def _citations(self):
        return ['Jonic2005', 'Sorzano2004b', 'Jin2014']

    def _methods(self):
        pass

    # --------------------------- UTILS functions --------------------------------------------
    def _printWarnings(self, *lines):
        """ Print some warning lines to 'warnings.xmd', 
        the function should be called inside the working dir."""
        fWarn = open("warnings.xmd", 'w')
        for l in lines:
            print >> fWarn, l
        fWarn.close()

    def _getLocalModesFn(self):
        modesFn = self.inputModes.get().getFileName()
        return self._getBasePath(modesFn)

    # def _updateParticle(self, item, row):
    #     setXmippAttributes(item, row, md.MDL_ANGLE_ROT, md.MDL_ANGLE_TILT, md.MDL_ANGLE_PSI, md.MDL_SHIFT_X,
    #                        md.MDL_SHIFT_Y, md.MDL_FLIP, md.MDL_NMA, md.MDL_COST)
    #     createItemMatrix(item, row, align=em.ALIGN_PROJ)
