# **************************************************************************
# *
# * Authors:
# * Ilyes Hamitouche
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


from pyworkflow.protocol.params import (PointerParam, StringParam, EnumParam,
                                        IntParam, LEVEL_ADVANCED)
import pyworkflow.protocol.params as params
from pwem.protocols import ProtAnalysis3D
from subprocess import check_call
import sys
import continuousflex


OPTION_NMA = 0
OPTION_ANGLES = 1
OPTION_SHFITS = 2
OPTION_ALL = 3

DEVICE_CUDA = 0
DEVICE_CPU = 1

class FlexProtDeepHEMNMAInfer(ProtAnalysis3D):
    """ This protocol is DeepHEMNMA
    """
    _label = 'deep hemnma infer'
    
    #--------------------------- DEFINE param functions --------------------------------------------
    def _defineParams(self, form):
        form.addSection(label='Input')
        form.addParam('analyze_option', params.EnumParam, label='set the parameter to predict',
                      display=params.EnumParam.DISPLAY_COMBO,
                      choices=['predict  normal mode amplitudes',
                               'predict on angles',
                               'predict on shifts',
                               'predict on shifts and angles',
                               ], default=OPTION_NMA,
                      help='select a set of parameter to predict')
        group = form.addGroup('Train on conformational variability',
                              condition='analyze_option == %d or analyze_option == %d' % (OPTION_NMA, OPTION_ALL))
        group.addParam('inputNMA', PointerParam, pointerClass='FlexProtAlignmentNMA',
                       label="Previous HEMNMA run",
                       help='Select a previous run of the NMA image alignment.', allowsNull=True)
        group = form.addGroup('Train on rigid-body variability ',
                              condition='analyze_option == %d or analyze_option == %d' % (OPTION_SHFITS, OPTION_ANGLES))
        form.addParam('device_option', params.EnumParam, label='set the device for training',
                      display=params.EnumParam.DISPLAY_COMBO,
                      choices=['train on GPUs',
                               'tain on CPUs'], default=DEVICE_CUDA,
                      help='set a device to run the training on')
        form.addParam('trained_model', params.PointerParam, pointerClass='FlexProtDeepHEMNMATrain',
                      label = 'Trained model', help='import the training weights')
        form.addParam('inputParticles', PointerParam, pointerClass='SetOfParticles',
                      label="Inference set",
                      help='TODO')
        form.addParallelSection(threads=0, mpi=0)    
    
    
    #--------------------------- INSERT steps functions --------------------------------------------

    def _insertAllSteps(self):
        pass
        # # Take deforamtions text file and the number of images and modes
        # inputSet = self.getInputParticles()
        # rows = inputSet.getSize()
        # reducedDim = self.reducedDim.get()
        # method = self.dimredMethod.get()
        # extraParams = self.extraParams.get('')
        #
        # deformationsFile = self.getDeformationFile()
        #
        # self._insertFunctionStep('convertInputStep',
        #                          deformationsFile, inputSet.getObjId())
        # self._insertFunctionStep('performDimredStep',
        #                          deformationsFile, method, extraParams,
        #                          rows, reducedDim)
        # self._insertFunctionStep('createOutputStep')
        
        
    #--------------------------- STEPS functions --------------------------------------------   
    
    def convertInputStep(self, deformationFile, inputId):
        pass
        # """ Iterate through the images and write the
        # plain deformation.txt file that will serve as
        # input for dimensionality reduction.
        # """
        # inputSet = self.getInputParticles()
        # f = open(deformationFile, 'w')
        #
        # for particle in inputSet:
        #     f.write(' '.join(particle._xmipp_nmaDisplacements))
        #     f.write('\n')
        # f.close()
    
    def performDeepHEMNMAStep(self):
        weights = self.trained_model.get()
        batch_size = self.batch_size.get()
        mode = self.analyze_option.get()
        device = self.device_option.get()
        self.imgsFn = self.inputParticles.get()._getExtraPath('images.xmd')
        params = " %s %s %d %d %d" % (self.imgsFn, weights, batch_size, mode, device)
        script_path = continuousflex.__path__[0]+'/protocols/utilities/deep_hemnma_infer.py'
        command = "python " + script_path + params
        check_call(command, shell=True, stdout=sys.stdout, stderr=sys.stderr, env=None, cwd=None)
        pass

        
    def createOutputStep(self):
        pass

    #--------------------------- INFO functions --------------------------------------------
    def _summary(self):
        summary = []
        return summary
    
    def _validate(self):
        errors = []
        return errors
    
    def _citations(self):
        return []
    
    def _methods(self):
        return []
    
    #--------------------------- UTILS functions --------------------------------------------

    def getInputParticles(self):
        """ Get the output particles of the input NMA protocol. """
        return self.inputNMA.get().outputParticles

    def getParticlesMD(self):
        "Get the metadata files that contain the NMA displacement"
        return self.inputNMA.get()._getExtraPath('images.xmd')

    def getInputPdb(self):
        return self.inputNMA.get().getInputPdb()
    
    def getOutputMatrixFile(self):
        return self._getExtraPath('output_matrix.txt')
    
    def getDeformationFile(self):
        return self._getExtraPath('deformations.txt')
    
    def getProjectorFile(self):
        return self.mappingFile.get()

