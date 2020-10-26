# **************************************************************************
# *
# * Authors:    Mohamad Harastani            (mohamad.harastani@upmc.fr)
# *             Slavica Jonic                (slavica.jonic@upmc.fr)
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
from continuousflex.protocols.data import PathData

"""
This module implement the wrappers around Xmipp CL2D protocol
visualization program.
"""

import os
from os.path import basename, join, exists, isfile
import numpy as np

import pwem.emlib.metadata as md

from pyworkflow.utils.path import cleanPath, makePath, cleanPattern
from pyworkflow.viewer import (ProtocolViewer, DESKTOP_TKINTER, WEB_DJANGO)

from pyworkflow.protocol.params import StringParam, LabelParam
from pwem.objects import SetOfParticles
from pyworkflow.utils.process import runJob
from pwem.viewers import VmdView
from pyworkflow.gui.browser import FileBrowserWindow
from continuousflex.protocols.protocol_heteroflow_dimred import FlexProtDimredHeteroFlow
from continuousflex.protocols.data import Point, Data
from .plotter_vol import FlexNmaVolPlotter
from continuousflex.viewers.nma_vol_gui import TrajectoriesWindowVol
from continuousflex.viewers.nma_vol_gui import ClusteringWindowVol
from joblib import load, dump
from continuousflex.protocols.utilities.spider_files3 import open_volume, save_volume
import farneback3d

from pwem.viewers.viewer_chimera import Chimera, ChimeraView


class FlexDimredHeteroFlowViewer(ProtocolViewer):
    """ Visualization of results from the NMA protocol
    """
    _label = 'viewer heteroflow dimred'
    _targets = [FlexProtDimredHeteroFlow]
    _environments = [DESKTOP_TKINTER, WEB_DJANGO]

    def __init__(self, **kwargs):
        ProtocolViewer.__init__(self, **kwargs)
        self._data = None

    def getData(self):
        if self._data is None:
            self._data = self.loadData()
        return self._data

    def _defineParams(self, form):
        form.addSection(label='Visualization')
        form.addParam('displayRawDeformation', StringParam, default='1',
                      label='Display raw deformation',
                      help='Type 1 to see the histogram of reduced dimensions, '
                           'using axis 1; \n '
                           'Type 2 to see the histogram of reduced dimensions, '
                           'using axis 2; etc. \n '
                           'Type 1 2 to see the histogram of reduced dimensions, using axes 1 and 2; \n'
                           'Type 1 2 3 to see the histogram of reduced dimensions, using axes 1, 2, '
                           'and 3; etc. '
                      )

        form.addParam('displayClustering', LabelParam,
                      label='Open clustering tool?',
                      help='Open a GUI to visualize the volumes as points '
                           'and select some of them to create new clusters, and compute 3D averages of the clusters')

        form.addParam('displayTrajectories', LabelParam,
                      label='Open trajectories tool?',
                      help='Open a GUI to visualize the volumes as points'
                           ' to draw and adjust trajectories.')

    def _getVisualizeDict(self):
        return {'displayRawDeformation': self._viewRawDeformation,
                'displayClustering': self._displayClustering,
                'displayTrajectories': self._displayTrajectories,
                }

    def _viewRawDeformation(self, paramName):
        components = self.displayRawDeformation.get()
        return self._doViewRawDeformation(components)

    def _doViewRawDeformation(self, components):
        components = list(map(int, components.split()))
        dim = len(components)
        views = []

        if dim > 0:
            modeList = [m - 1 for m in components]
            modeNameList = ['Principle Component Axis %d' % m for m in components]
            missingList = []

            if missingList:
                return [self.errorMessage("Invalid mode(s) *%s*\n." % (', '.join(missingList)),
                                          title="Invalid input")]

            # Actually plot
            plotter = FlexNmaVolPlotter(data=self.getData())
            baseList = [basename(n) for n in modeNameList]

            self.getData().XIND = modeList[0]
            if dim == 1:
                plotter.plotArray1D("Histogram of reduced dimensions deformation amplitudes: %s" % baseList[0],
                                    "Amplitude", "Number of volumes")
            else:
                self.getData().YIND = modeList[1]
                if dim == 2:
                    plotter.plotArray2D("Reduced dimensions deformation amplitudes: %s vs %s" % tuple(baseList),
                                        *baseList)
                elif dim == 3:
                    self.getData().ZIND = modeList[2]
                    plotter.plotArray3D("Reduced dimensions deformation amplitudes: %s %s %s" % tuple(baseList),
                                        *baseList)
            views.append(plotter)

        return views

    def _displayClustering(self, paramName):
        self.clusterWindow = self.tkWindow(ClusteringWindowVol,
                                           title='Volume Clustering Tool',
                                           dim=self.protocol.reducedDim.get(),
                                           data=self.getData(),
                                           callback=self._createCluster
                                           )
        return [self.clusterWindow]

    def _displayTrajectories(self, paramName):
        self.trajectoriesWindow = self.tkWindow(TrajectoriesWindowVol,
                                                title='Trajectories Tool',
                                                dim=self.protocol.reducedDim.get(),
                                                data=self.getData(),
                                                callback=self._generateAnimation,
                                                loadCallback=self._loadAnimation,
                                                numberOfPoints=10
                                                )
        return [self.trajectoriesWindow]

    def _createCluster(self):
        """ Create the cluster with the selected particles
        from the cluster. This method will be called when
        the button 'Create Cluster' is pressed.
        """
        # Write the particles
        prot = self.protocol
        project = prot.getProject()
        inputSet = prot.getInputParticles().get()
        fnSqlite = prot._getTmpPath('cluster_particles.sqlite')
        cleanPath(fnSqlite)
        partSet = SetOfParticles(filename=fnSqlite)
        partSet.copyInfo(inputSet)
        first = True
        for point in self.getData():
            if point.getState() == Point.SELECTED:
                particle = inputSet[point.getId()]
                partSet.append(particle)
        partSet.write()
        partSet.close()

        from continuousflex.protocols.protocol_batch_cluster_heteroflow import FlexBatchProtHeteroFlowCluster

        newProt = project.newProtocol(FlexBatchProtHeteroFlowCluster)
        clusterName = self.clusterWindow.getClusterName()
        if clusterName:
            newProt.setObjLabel(clusterName)
        newProt.inputHeteroFlowDimred.set(prot)
        newProt.sqliteFile.set(fnSqlite)
        project.launchProtocol(newProt)
        project.getRunsGraph()




    def _loadAnimationData(self, obj):
        pass
        # prot = self.protocol
        # animationName = obj.getFileName()  # assumes that obj.getFileName is the folder of animation
        # animationPath = prot._getExtraPath(animationName)
        # # animationName = animationPath.split('animation_')[-1]
        # animationRoot = join(animationPath, animationName)
        #
        # animationSuffixes = ['.vmd', '.pdb', 'trajectory.txt']
        # for s in animationSuffixes:
        #     f = animationRoot + s
        #     if not exists(f):
        #         self.errorMessage('Animation file "%s" not found. ' % f)
        #         return
        #
        # # Load animation trajectory points
        # trajectoryPoints = np.loadtxt(animationRoot + 'trajectory.txt')
        # data = PathData(dim=trajectoryPoints.shape[1])
        #
        # for i, row in enumerate(trajectoryPoints):
        #     data.addPoint(Point(pointId=i + 1, data=list(row), weight=1))
        #
        # self.trajectoriesWindow.setPathData(data)
        # self.trajectoriesWindow.setAnimationName(animationName)
        # self.trajectoriesWindow._onUpdateClick()
        #
        # def _showVmd():
        #     vmdFn = animationRoot + '.vmd'
        #     VmdView(' -e %s' % vmdFn).show()
        #
        # self.getTkRoot().after(500, _showVmd)
        pass

    def _loadAnimation(self):
        prot = self.protocol
        browser = FileBrowserWindow("Select the animation folder (animation_NAME)",
                                    self.getWindow(), prot._getExtraPath(),
                                    onSelect=self._loadAnimationData)
        browser.show()

    def _generateAnimation(self):
        prot = self.protocol
        # This is not getting the file correctly, we are workingaround it:
        # projectorFile = prot.getProjectorFile()
        projectorFile = prot._getExtraPath() + '/projector.txt'
        if isfile(projectorFile):
            print('Mapping found, the animation is exact inverse of the dimensionality reduction method')
        else:
            print('Mapping not found, the animation is an estimation of reversing the dimensionality reduction method')

        animation = self.trajectoriesWindow.getAnimationName()
        animationPath = prot._getExtraPath('animation_%s' % animation)

        cleanPath(animationPath)
        makePath(animationPath)
        animationRoot = join(animationPath, 'animation_%s' % animation)
        trajectoryPoints = np.array([p.getData() for p in self.trajectoriesWindow.pathData])

        if isfile(projectorFile):
            M = np.loadtxt(projectorFile)
            if prot.getMethodName()=='sklearn_PCA':
                pca = load(prot._getExtraPath('pca_pickled.txt'))
                deformations = pca.inverse_transform(trajectoryPoints)
            else:
                # TODO: add mean
                deformations = np.dot(trajectoryPoints, np.linalg.pinv(M))
            np.savetxt(animationRoot + 'trajectory.txt', trajectoryPoints)
        else:
            Y = np.loadtxt(prot.getOutputMatrixFile())
            X = np.loadtxt(prot.getDeformationFile())
            # Find closest points in deformations
            deformations = [X[np.argmin(np.sum((Y - p) ** 2, axis=1))] for p in trajectoryPoints]

        # get the original size of the input:
        mdImgs = md.MetaData(self.protocol.inputOpFlow.get()._getExtraPath('volumes.xmd'))
        N = 0
        for objId in mdImgs:
            N += 1

        # reading back all optical flows
        bigmat = []
        if(isfile(self.protocol._getExtraPath('bigmat_inverse.pkl'))):
            print('bigmat_inverse.txt found')
            # bigmat_pinv = np.loadtxt(self.protocol._getExtraPath('bigmat_inverse.txt'))
            bigmat_pinv = load(self.protocol._getExtraPath('bigmat_inverse.pkl'))
        else:
            if(isfile(self.protocol._getExtraPath('bigmat.pkl'))):
                bigmat = load(self.protocol._getExtraPath('bigmat.pkl'))
            else:
                for j in range(1, N+1):
                    flowj = self.read_optical_flow_by_number(j)
                    flowj = np.reshape(flowj, [3 * np.shape(flowj)[1] * np.shape(flowj)[2] * np.shape(flowj)[3]])
                    bigmat.append(flowj)
                bigmat = np.array(bigmat)
                # np.savetxt(self.protocol._getExtraPath('bigmat.txt'),bigmat)
                dump(bigmat,self.protocol._getExtraPath('bigmat.pkl'))
            bigmat_pinv = np.linalg.pinv(bigmat)
            bigmat = None  # removing it from the memory
            # np.savetxt(self.protocol._getExtraPath('bigmat_inverse.txt'),bigmat_pinv)
            dump(bigmat_pinv,self.protocol._getExtraPath('bigmat_inverse.pkl'))

        line = np.matmul(bigmat_pinv, np.transpose(deformations))
        bigmat_pinv = None # removing if from the memory
        fnref = self.protocol._getExtraPath('reference.spi')
        shape = np.shape(open_volume(fnref))

        for i, trash in enumerate(deformations):
            flowi = np.transpose(line[:, i])
            flowi = np.reshape(flowi, [3, shape[0], shape[1], shape[2]])
            pathi = animationRoot + str(i).zfill(3) + 'deformed_by_opflow.vol'
            ref = open_volume(fnref)
            ref = farneback3d.warp_by_flow(ref, np.float32(flowi))
            save_volume(ref, pathi)
        fn_cxc = self.protocol._getExtraPath('chimera.cxc')
        # cxc_command = 'open ' + animationPath + '/*.vol vseries true\n'
        cxc_command = 'open animation_/*.vol vseries true\n'
        cxc_command += 'vseries play #1 loop true maxFrameRate 5 direction oscillate'
        with open(fn_cxc, 'w') as f:
            print(cxc_command, file=f)
        # ChimeraView(fn_cxc)
        command = '$SCIPION_HOME/$CHIMERA_HOME/bin/ChimeraX ' + fn_cxc
        os.system(command)




    def loadData(self):
        """ Iterate over the images and their deformations
        to create a Data object with theirs Points.
        """
        particles = self.protocol.getInputParticles().get()
        mat = np.loadtxt(self.protocol._getExtraPath('output_matrix.txt'))
        data = Data()
        for i, particle in enumerate(particles):
            pointData = mat[i,:]
            data.addPoint(Point(pointId=particle.getObjId(),
                                data=pointData,
                                weight=0))
            # print(pointData)
        return data

    def _validate(self):
        errors = []
        return errors

    def read_optical_flow(self, path_flowx, path_flowy, path_flowz):
        x = open_volume(path_flowx)
        y = open_volume(path_flowy)
        z = open_volume(path_flowz)
        l = np.shape(x)
        # print(l)
        flow = np.zeros([3, l[0], l[1], l[2]])
        flow[0, :, :, :] = x
        flow[1, :, :, :] = y
        flow[2, :, :, :] = z
        return flow

    def read_optical_flow_by_number(self, num):
        op_path = self.protocol.inputOpFlow.get()._getExtraPath()+'/optical_flows/'
        # op_path = self._getExtraPath() + '/optical_flows/'
        path_flowx = op_path + str(num).zfill(6) + '_opflowx.spi'
        path_flowy = op_path + str(num).zfill(6) + '_opflowy.spi'
        path_flowz = op_path + str(num).zfill(6) + '_opflowz.spi'
        flow = self.read_optical_flow(path_flowx, path_flowy, path_flowz)
        return flow
