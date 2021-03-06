from Stats import StatsReporter
from Stats import ParamsContainer
import datetime
from PlayerPython import * 
import CompuCellSetup
from PySteppables import *
from PySteppablesExamples import MitosisSteppableBase
import CompuCell
import sys
import math
from decimal import *
from random import random
from copy import deepcopy
import numpy as np

class HistPlotSteppable(SteppableBasePy):
    def __init__(self,_simulator,_frequency=10):
    	SteppableBasePy.__init__(self,_simulator,_frequency)

    def start(self):
        #initialize setting for Histogram
        self.pW = self.addNewPlotWindow(_title='Cell Volumes',
                                        _xAxisTitle='Volume',
                                        _yAxisTitle='Count')
        self.pW.addHistogramPlot(_plotName='Hist 1',_color='green',_alpha=100)
        
        self.pW2 = self.addNewPlotWindow(_title='Avg Cell Volume and targetVolume',
                                       _xAxisTitle = 'MonteCarlo Step (MCS)',
                                       _yAxisTitle = 'Pixels**2')
                                       
        self.pW2.addPlot('AvgVol', _style='Dots', _color='red', _size=5)
        self.pW2.addPlot('AvgTargetVol', _style='Dots', _color='blue', _size=5)
        
    def step(self,mcs):
        volume_list = [cell.volume for cell in self.cellList]
        n, bins = np.histogram(volume_list, bins=25)
        self.pW.addHistPlotData('Hist 1', n, bins)
        self.pW.showAllHistPlots()
        
        num_cells = len(self.cellListByType(self.GZ))
        avg_vol = Decimal(sum(cell.volume for cell in self.cellListByType(self.GZ))) / Decimal(num_cells)
        avg_tar_vol = Decimal(sum(cell.targetVolume for cell in self.cellListByType(self.GZ))) / Decimal(num_cells)
        self.pW2.addDataPoint('AvgVol', mcs, avg_vol)
        self.pW2.addDataPoint('AvgTargetVol', mcs, avg_tar_vol)
        self.pW2.showAllPlots()
        
        
class VolumeStabilizer(SteppableBasePy):
    def __init__(self,_simulator,_frequency,_params_container):
        SteppableBasePy.__init__(self,_simulator,_frequency)
        self.params_container=_params_container

    def start(self):
        for cell in self.cellList:
            cell.targetSurface=cell.surface 
            cell.targetVolume=cell.volume + 4
            # In practice, there is always an aproximately 4 pixel difference between the actual
            # volume and the targetVolume. We add 4 to the targetVolume initially to keep this
            # consistent throughout the simulation.
            
            cell.lambdaVolume = 50.0 # A high lambdaVolume makes the cells resist changing volume.
            cell.lambdaSurface = 2.0 # However, a low lambdaSurface still allows them to move easily.
            # In effect, these above two lines allow the cells to travel without squeezing, which would be unrealistic.

class SimplifiedForces_SmoothedForces(SteppableBasePy):
    def __init__(self,_simulator,_frequency, _params_container, _stats_reporter):
      SteppableBasePy.__init__(self,_simulator,_frequency)
      self.reporter = _stats_reporter
      self.params_container = _params_container

      # Set the constants for the AP force function
      self.V_AP_GZposterior = self.params_container.getNumberParam('V_AP_GZposterior')
      self.k1_AP_GZanterior = self.params_container.getNumberParam('k1_AP_GZanterior')  
      self.k2_AP_GZanterior = self.params_container.getNumberParam('k2_AP_GZanterior')  
      self.k1_AP_Segments = self.params_container.getNumberParam('k1_AP_Segments')  
      self.k2_AP_Segments = self.params_container.getNumberParam('k2_AP_Segments')
      
      # Set the constants for the ML force function
      self.k1_ML_GZ = self.params_container.getNumberParam('k1_ML_GZ')  
      self.k2_ML_GZ = self.params_container.getNumberParam('k2_ML_GZ')
      self.k1_ML_Segments = self.params_container.getNumberParam('k1_ML_Segments')  
      self.k2_ML_Segments = self.params_container.getNumberParam('k2_ML_Segments')
      
    def start(self):
      self.anterior0=self.find_posterior_EN()
      self.posterior0=self.find_posterior_GZ()
      
    
   # Define the AP force function
    def AP_potential_function(self,mcs,x,y):
      # Set the constants for the AP force function

      if y < self.anterior: # if posterior to first EN stripe
         if (y-self.posterior)/(self.anterior-self.posterior) < 0.5:
            V=self.V_AP_GZposterior # 70
         else:
            k1=self.k1_AP_GZanterior
            k2=self.k2_AP_GZanterior
              
            V=k1/0.5*((self.anterior-y)/(self.anterior-self.posterior))+k2
         
      else:
         k1=self.k1_AP_Segments
         k2=self.k2_AP_Segments
         V=k1*math.exp(k2*abs((y-self.anterior)))
      return V
      
   # Define the ML force function
    def ML_potential_function(self,mcs,x,y):
      # Set the constants for the ML force function
      if y < self.anterior: # if posterior to first EN stripe
         k1=self.k1_ML_GZ
         k2=self.k2_ML_GZ
      else:
         k1=self.k1_ML_Segments
         k2=self.k2_ML_Segments         
            
      if x<self.midline:
         k1=-1*k1
      
      V=k1*math.exp(k2*abs(self.anterior-y))
      # V=0
      return V       
      
    def step(self,mcs):
      self.midline=self.find_midline()
      self.anterior=self.find_posterior_EN()
      self.posterior=self.find_posterior_GZ()
      for cell in self.cellList:
         x=cell.xCOM
         y=cell.yCOM
         V_y=self.AP_potential_function(mcs,x,y)
         V_x=self.ML_potential_function(mcs,x,y)
         cell.lambdaVecX=V_x
         cell.lambdaVecY=V_y

      
    def find_midline(self):
      x0 = min(cell.xCOM for cell in self.cellList)
      x_max = max(cell.xCOM for cell in self.cellList)
      midline=x0+0.5*(x_max-x0)
      return midline
      
    def find_posterior_EN(self):
      y_EN_pos = min(cell.yCOM for cell in self.cellListByType(2)) # EN cell
      return y_EN_pos

    def find_posterior_GZ(self):
      y_GZ_pos = min(cell.yCOM for cell in self.cellList)
      return y_GZ_pos       

class SarrazinVisualizer(SteppableBasePy):
    def __init__(self, _simulator, _frequency):
        SteppableBasePy.__init__(self, _simulator, _frequency)
        self.vectorCLField = self.createVectorFieldCellLevelPy('Sarrazin_Force')

    def step(self, mcs):
        self.vectorCLField.clear()
        for cell in self.cellList:
            self.vectorCLField[cell] = [cell.lambdaVecX * -1, cell.lambdaVecY * -1, 0]

class Engrailed(SteppableBasePy):
    def __init__(self,_simulator,_frequency,_params_container, _hinder_anterior_cells,_embryo_size):
        SteppableBasePy.__init__(self,_simulator,_frequency)
        self.hinder_anterior_cells = _hinder_anterior_cells
        self.params_container=_params_container
        self.gene_product_field = None
        self.gene_product_secretor = None
        self.stripe_y = None

        # Set stripe positioning parameters based on the Piff file
        if _embryo_size==1:
            self.initial_stripe=805
            self.stripe_width=20
            self.stripe_spacing=50

        else:
            self.initial_stripe=1610
            self.stripe_width=30
            self.stripe_spacing=100

        self.stripe_period = self.params_container.getNumberParam('stripe_period')

    def start(self):
        if self.hinder_anterior_cells:
            self.gene_product_field = CompuCell.getConcentrationField(self.simulator,'EN_GENE_PRODUCT')
            self.gene_product_secretor = self.getFieldSecretor('EN_GENE_PRODUCT')

        for cell in self.cellList: # THIS BLOCK HAS BEEN JUSTIFIED OUTSIDE OF EARLIER 'IF' STATEMENT (sdh)
            self.stripe_y = self.initial_stripe 
            if cell.yCOM < self.stripe_y+self.stripe_width/2 and cell.yCOM > self.stripe_y-self.stripe_width/2:
                cell.type = 2 # EN cell
                if self.hinder_anterior_cells == True:
                     self.gene_product_secretor.secreteInsideCell(cell, 1)

    def step(self, mcs):
        if (mcs != 0) and (mcs % self.stripe_period == 0) :
            self.stripe_y -= self.stripe_spacing
            for cell in self.cellList:
                if cell:
                    if cell.yCOM < self.stripe_y + (self.stripe_width/2+1) and cell.yCOM > self.stripe_y - (self.stripe_width/2+1):
                        cell.type = 2 # EN

class OrientedConstraintSteppable(SteppableBasePy):
    def __init__(self, _simulator, _frequency, _OGPlugin):
        SteppableBasePy.__init__(self, _simulator, _frequency)
        self.OGPlugin = _OGPlugin

    def start(self):
        for cell in self.cellList:
            if cell:
                cell.targetVolume = cell.volume

                self.OGPlugin.setElongationAxis(cell, 0, 1)  # Here, we define the axis of elongation.
                self.OGPlugin.setConstraintWidth(cell, 4.0)  # And this function gives a width constraint to each cell
                self.OGPlugin.setElongationEnabled(cell, True)  # Make sure to enable or disable elongation in all cells
                # Or unexpected results may occur.

class DyeCells(SteppableBasePy):
    '''Labels a population of cells and outputs to a Player visualization field'''

    def __init__(self, _simulator, _frequency, _x0, _y0, _xf, _yf, _reporter):
        SteppableBasePy.__init__(self, _simulator, _frequency)
        self.pixelTrackerPlugin = CompuCell.getPixelTrackerPlugin()
        self.x0 = _x0;
        self.xf = _xf
        self.y0 = _y0;
        self.yf = _yf
        self.reporter = _reporter

    def setScalarField(self, _field):
        self.dyeField = _field

    def start(self):
        self.zero_field()
        self.zero_cells()
        for i in range(len(self.x0)):
            dye = 1 + i
            x0 = self.x0[i]
            xf = self.xf[i]
            y0 = self.y0[i]
            yf = self.yf[i]
            self.mark_clone(x0, xf, y0, yf, dye)

    def step(self, mcs):
        # Identify cells that have dye and visualize the dye in Player
        self.zero_field()
        for cell in self.cellList:
            if cell:
                cellDict = CompuCell.getPyAttrib(cell)
                dye = cellDict['dye']
                if dye > 0:
                    pixelList = CellPixelList(self.pixelTrackerPlugin, cell)
                    for pixelData in pixelList:
                        pt = pixelData.pixel
                        fillScalarValue(self.dyeField, pt.x, pt.y, pt.z, dye)

    def mark_clone(self, x0, xf, y0, yf, dye):
        for cell in self.cellList:
            if cell:
                cellDict = CompuCell.getPyAttrib(cell)
                xCM = cell.xCOM
                yCM = cell.yCOM
                if (xCM >= x0 and xCM <= xf and yCM >= y0 and yCM <= yf):  ## if the cell is within the dye area
                    cellDict['dye'] = dye  ## set initial dye load
                    pixelList = CellPixelList(self.pixelTrackerPlugin, cell)
                    for pixelData in pixelList:
                        pt = pixelData.pixel
                        fillScalarValue(self.dyeField, pt.x, pt.y, pt.z, dye)

    def zero_field(self):
        # Set dye field to zero
        for x in range(self.dim.x):
            for y in range(self.dim.y):
                fillScalarValue(self.dyeField, x, y, 0, 0)

    def zero_cells(self):
        for cell in self.cellList:
            if cell:
                cellDict = CompuCell.getPyAttrib(cell)
                cellDict['dye'] = 0

class DyeMitosisClones(SteppableBasePy):
    def __init__(self, _simulator, _frequency, _window):
        SteppableBasePy.__init__(self, _simulator, _frequency)
        self.pixelTrackerPlugin = CompuCell.getPixelTrackerPlugin()
        self.window = _window

    def setScalarField(self, _field):
        self.dyeField = _field

    def start(self):
        ### Initialize mitosis dye value to zero in all cells
        for cell in self.cellList:
            if cell:
                cellDict = CompuCell.getPyAttrib(cell)
                cellDict['mitosis_dye'] = 0

    def step(self, mcs):
        ### if within the mitosis dye window, mark mitosing cells (this will depend on the
        ### visualization of mitosing cells by marking them as type 'Mitosing')
        if mcs >= self.window[0] and mcs <= self.window[1]:
            for cell in self.cellList:
                if cell.type == 4:  # if a type Mitosing cell
                    cellDict = CompuCell.getPyAttrib(cell)
                    cellDict['mitosis_dye'] = 1

                    ##### Set mitosis dye field to zero
        for x in range(self.dim.x):
            for y in range(self.dim.y):
                fillScalarValue(self.dyeField, x, y, 0, 0)
                ##### identify cells that have mitosis dye and visualize the dye in Player
        for cell in self.cellList:
            if cell:
                cellDict = CompuCell.getPyAttrib(cell)
                dye = cellDict['mitosis_dye']
                if dye > 0:
                    pixelList = CellPixelList(self.pixelTrackerPlugin, cell)
                    for pixelData in pixelList:
                        pt = pixelData.pixel
                        fillScalarValue(self.dyeField, pt.x, pt.y, pt.z, dye)

class Measurements(SteppableBasePy):
    def __init__(self, _simulator, _frequency, _reporter, _output_path, _batch=False, _batch_iteration=0):
        SteppableBasePy.__init__(self, _simulator, _frequency)
        self.reporter = _reporter
        self.outp = _output_path
        self.batch = _batch
        self.batch_iteration = _batch_iteration

    def start(self):
        try:
            output_folder = self.outp
            stamp = datetime.datetime.fromtimestamp(time.time()).strftime('%y%m%d-%H%M%S')
            if not self.batch:
                self.output_filename = output_folder + 'run' + stamp + '.csv'
            else:
                self.output_filename = self.fname = '{}batch_run_{}.csv'.format(output_folder, self.batch_iteration)
            with open(self.output_filename, 'w') as self.output_file:
                measurement_vars = ['MCS', 'GB cell count', 'GB length', 'GB area', 'GB cell divisions',
                                    'GZ cell count', 'GZ length', 'GZ area', 'GZ cell divisions',
                                    'avg division cycle time', 'GZ div / GZ area']
                output_str = ','.join(measurement_vars) + '\n'
                self.output_file.write(output_str)
        except IOError:
            raise NameError('Could not output to a csv file properly! Aborting.')

        getcontext().prec = 15 # Sets the decimal precision for high precision arithmetic

    def step(self, mcs):
        print('\nTaking measurements @ {} mcs'.format(mcs))
        with open(self.output_filename, 'a') as self.output_file:
            GZ_division = self.find_GZ_division_count()
            GB_division = self.find_GB_division_count()
            GB_cell_count = self.find_GB_cell_count()
            GZ_cell_count = self.find_GZ_cell_count()
            GB_length = self.find_GB_length()
            GZ_length = self.find_GZ_length()
            GB_area = self.find_GB_area()
            GZ_area = self.find_GZ_area()
            GZ_normalized_growth = Decimal(GZ_division) / Decimal(GZ_area) # Decimal() allows high precision arithmetic
            avg_cell_size = self.find_average_cell_size()
            avg_diam = math.sqrt(avg_cell_size)
            avg_div_time = self.find_avg_div_time()

            measurements_vars = [mcs, GB_cell_count, GB_length, GB_area, GB_division, GZ_cell_count, GZ_length, GZ_area,
                                 GZ_division, avg_div_time, GZ_normalized_growth]
            str_rep_measurements_vars = (str(var) for var in measurements_vars)

            self.output_file.write(','.join(str_rep_measurements_vars))
            self.output_file.write('\n')

    def find_avg_div_time(self):
        sum_times = 0
        num_times = 0
        for cell in self.cellList:
            if cell:
                cellDict = CompuCell.getPyAttrib(cell)
                if 'mitosis_times' in cellDict:
                    if len(cellDict['mitosis_times']) > 1:
                        sum_times += sum(cellDict['mitosis_times']) - cellDict['mitosis_times'][0]
                        num_times += len(cellDict['mitosis_times']) - 1
        if num_times == 0:
            avg_time = 0
        else:
            avg_time = sum_times / float(num_times)
        return avg_time

    def find_GZ_division_count(self):
        division_count = 0
        for cell in self.cellList:
            if cell:
                cellDict = CompuCell.getPyAttrib(cell)
                division_count += cellDict['divided_GZ']
                cellDict['divided_GZ'] = 0
        return division_count

    def find_GB_division_count(self):
        division_count = 0
        for cell in self.cellList:
            if cell:
                cellDict = CompuCell.getPyAttrib(cell)
                division_count += cellDict['divided']
                cellDict['divided'] = 0
        return division_count

    def find_GB_cell_count(self):
        GB_cell_count = sum(1 for cell in self.cellList if cell)
        return GB_cell_count

    def find_GZ_cell_count(self):
        y_EN_pos = self.find_posterior_EN_stripe()
        GZ_cell_count = sum(1 for cell in self.cellList if cell.yCOM < y_EN_pos)
        return GZ_cell_count

    def find_GB_length(self):
        ant = self.find_anterior_GB()
        pos = self.find_posterior_GB()
        length = ant - pos
        return length

    def find_GZ_length(self):
        ant = self.find_posterior_EN_stripe()
        pos = self.find_posterior_GB()
        length = ant - pos
        return length

    def find_GB_area(self):
        area = sum(cell.volume for cell in self.cellList)
        return area

    def find_GZ_area(self):
        y_ant = self.find_posterior_EN_stripe()
        area = sum(cell.volume for cell in self.cellList if cell.yCOM < y_ant)
        return area

    def find_average_cell_size(self):
        area = self.find_GB_area()
        cell_count = self.find_GB_cell_count()
        avg_cell_volume = area / cell_count
        return avg_cell_volume

    def find_posterior_EN_stripe(self):
        EN_posterior = min(cell.yCOM for cell in self.cellListByType(2)) # EN cell
        return EN_posterior

    def find_anterior_GB(self):
        GB_anterior = max(cell.yCOM for cell in self.cellList)
        return GB_anterior

    def find_posterior_GB(self):
        GB_posterior = min(cell.yCOM for cell in self.cellList)
        return GB_posterior

class ElongationMitosisSteppableBase(MitosisSteppableBase):

    def __init__(self, _simulator, _frequency, _params_container, _stats_reporter):
        MitosisSteppableBase.__init__(self, _simulator, _frequency)

        self.reporter = _stats_reporter
        self.params_container = _params_container

        self.y_GZ_mitosis_border_percent = self.params_container.getNumberParam('y_GZ_mitosis_border_percent')
        self.transition_times = self.params_container.getListParam('mitosis_transition_times')
        self.transition_counter = 0  ## current simulation time window
        self.r_mitosis_R0 = self.params_container.getListParam('r_mitosis_R0')  # e.g. [0.0, 0.0, 0.0]
        self.r_mitosis_R1 = self.params_container.getListParam('r_mitosis_R1')  # e.g. [0.0, 0.0, 0.0]
        self.r_mitosis_R2 = self.params_container.getListParam('r_mitosis_R2')  # e.g. [0.0, 0.5, 0.0]
        self.r_mitosis_R3 = self.params_container.getListParam('r_mitosis_R3')  # e.g. [0.5, 0.5, 0.5]
        self.r_grow_R0 = self.params_container.getListParam('r_grow_R0')  # e.g. [0.0,0.0,0.0]
        self.r_grow_R1 = self.params_container.getListParam('r_grow_R1')  # e.g. [0.0,0.0,0.0]
        self.r_grow_R2 = self.params_container.getListParam('r_grow_R2')  # e.g [0.0,0.0,0.0]
        self.r_grow_R3 = self.params_container.getListParam('r_grow_R3')  # e.g. [0.05,0.05,0.05]
        self.r_grow_list = [self.r_grow_R0[0], self.r_grow_R1[0], self.r_grow_R2[0], self.r_grow_R3[0]]
        self.fraction_AP_oriented = self.params_container.getNumberParam('mitosis_fraction_AP_oriented')
        self.window = self.params_container.getNumberParam('mitosis_window')
        self.Vmin_divide = self.params_container.getNumberParam('mitosis_Vmin_divide')
        self.Vmax = self.params_container.getNumberParam('mitosis_Vmax')
        self.mitosisVisualizationFlag = self.params_container.getNumberParam('mitosis_visualization_flag')
        self.mitosisVisualizationWindow = self.params_container.getNumberParam('mitosis_visualization_window')

    def assign_cell_region(self, cell):
        cell_dict = CompuCell.getPyAttrib(cell)
        yCM = cell.yCM / float(cell.volume)
        if yCM > self.y_EN_ant:  # if cell is anterior to EN stripes
            cell_dict['region'] = 0
            if cell.type != 4 and cell.type != 2 :  # if cell is not En or mitosing
                cell.type = 1  # AnteriorLobe
        elif yCM > self.y_EN_pos:  # if cell is in EN-striped region
            cell_dict['region'] = 1
            if cell.type != 2 and cell.type != 4 and cell.type != 1:  # if cell is not En or mitosing or AnteriorLobe
                cell.type = 5  # Segmented
        elif yCM > self.y_GZ_border:  # if cell is in anterior region of GZ
            cell_dict['region'] = 2
            if (cell.type != 2 and cell.type != 4):  # if cell is not En or mitosing
                cell.type = 3  # GZ
        else:  # if cell is in posterior region of GZ
            cell_dict['region'] = 3
            if cell.type != 4:  # if cell is not mitosing
                cell.type = 3  # GZ

    def updateAttributes(self):
        '''
        UpdateAttributes is inherited from MitosisSteppableBase
        and is called automatically by the divideCell() function.
        It sets the attributes of the parent and daughter cells
        '''
        parent_cell = self.mitosisSteppable.parentCell
        child_cell = self.mitosisSteppable.childCell

        child_cell.targetVolume = child_cell.volume
        child_cell.lambdaVolume = parent_cell.lambdaVolume
        child_cell.targetSurface = child_cell.surface
        child_cell.lambdaSurface = parent_cell.lambdaSurface
        parent_cell.targetVolume = parent_cell.volume
        parent_cell.targetSurface = parent_cell.surface
        child_cell.type = parent_cell.type

        parent_dict = CompuCell.getPyAttrib(parent_cell)
        child_dict = CompuCell.getPyAttrib(child_cell)
        parent_dict.get('mitosis_times',[]).append(self.mcs - parent_dict.get('last_division_mcs',self.mcs))
        parent_dict['last_division_mcs'] = self.mcs

        # Make a copy of the parent cell's dictionary and attach to child cell
        for key, item in parent_dict.iteritems():
            child_dict[key] = deepcopy(item)
        child_dict['mitosis_times'] = []

    def visualize_mitosis(self, cell):
        cell_dict = CompuCell.getPyAttrib(cell)
        cell_dict['mitosisVisualizationTimer'] = self.mitosisVisualizationWindow
        cell_dict['returnToCellType'] = cell.type
        cell.type = 4  # set to mitosing cell

    def mitosis_visualization_countdown(self):
        for cell in self.cellListByType(4): # Mitosis cell
            cellDict = CompuCell.getPyAttrib(cell)
            if cellDict['mitosisVisualizationTimer'] <= 0:
                cell.type = cellDict['returnToCellType']
            else:
                cellDict['mitosisVisualizationTimer'] -= 1

    def perform_mitosis(self, mitosis_list):
        for cell in mitosis_list:
            if self.mitosisVisualizationFlag:
                self.visualize_mitosis(cell)  # change cell type to 'Mitosing'

            # Choose whether cell will divide along AP or random orientation
            AP_divide = random()
            if AP_divide <= self.fraction_AP_oriented:
                self.divideCellOrientationVectorBased(cell, 0, 1, 0)
            else:
                self.divideCellRandomOrientation(cell)

        if self.mitosisVisualizationFlag:
            self.mitosis_visualization_countdown()  # Maintains cell type as 'Mitosing' for a set window of time (self.mitosisVisualizationWindow)

    def initiate_cell_volume(self, cell):
        phase = random()  # chooses a phase between 0 and 1 to initialize cell volume
        volume_difference = self.Vmin_divide - cell.volume
        new_volume = phase * volume_difference + cell.volume
        cell.targetVolume = new_volume

    def attach_growth_timer(self, cell):
        phase = random()  # picks a random phase between 0 and 1 to initialize cell growth timer
        growth_timer = phase
        return growth_timer

    def grow_cell(self, cell):
        cellDict = CompuCell.getPyAttrib(cell)
        region = cellDict['region']
        r_grow = self.r_grow_list[region]
        if cellDict['growth_timer'] >= 1:
            if cell.targetVolume <= self.Vmax:
                cell.targetVolume += int(cellDict['growth_timer'])
                cellDict['growth_timer'] = 0
        else:
            cellDict['growth_timer'] += r_grow

    def make_mitosis_list(self):
        mitosis_list = []
        for cell in self.cellList:
            cellDict = CompuCell.getPyAttrib(cell)
            region = cellDict['region']
            mitosis_probability = self.r_mitosis_list[region] / self.window
            if mitosis_probability >= random():
                if cell.volume >= self.Vmin_divide:
                    mitosis_list.append(cell)
                    cellDict['divided'] = 1
                    if cell.type == 3:  # if GZ cell
                        cellDict['divided_GZ'] = 1
        return mitosis_list

    def find_posterior_EN_stripe(self):
        y_EN_pos = min(cell.yCM / float(cell.volume) for cell in self.cellListByType(2)) # EN cell
        return y_EN_pos

    def find_anterior_EN_stripe(self):
        y_EN_ant = max(cell.yCM / float(cell.volume) for cell in self.cellListByType(2)) # EN cell
        return y_EN_ant

    def find_posterior_GZ(self):
        y_GZ_pos = min(cell.yCM / float(cell.volume) for cell in self.cellList) # EN cell
        return y_GZ_pos

    def find_y_GZ_mitosis_border(self):
        y_GZ_pos = self.find_posterior_GZ()
        y_GZ_border = y_GZ_pos + self.y_GZ_mitosis_border_percent * (self.y_EN_pos - y_GZ_pos)
        return y_GZ_border

class RegionalMitosis(ElongationMitosisSteppableBase):
      
   def start(self):
      self.y_EN_pos=self.find_posterior_EN_stripe()
      self.y_EN_ant=self.find_anterior_EN_stripe()
      self.y_GZ_border=self.find_y_GZ_mitosis_border()
      for cell in self.cellList:
         region=self.assign_cell_region(cell)
         cellDict = CompuCell.getPyAttrib(cell)
         cellDict['growth_timer']=self.attach_growth_timer(cell)  ## attached a countdown timer for cell growth
         cellDict['divided']=0
         cellDict['divided_GZ']=0
         cellDict['mitosis_times']=[]
         cellDict['last_division_mcs']=0
   
   def step(self,mcs):
      self.mcs=mcs
      #print '\nExecuting Mitosis Steppable @ {}'.format(mcs)
      if mcs in self.transition_times:
         print '*******************TRANSITIONING MITOSIS TIME WINDOW**********************'
         self.reporter.printLn( '*******************TRANSITIONING MITOSIS TIME WINDOW**********************')
         self.r_mitosis_list=[self.r_mitosis_R0[self.transition_counter],self.r_mitosis_R1[self.transition_counter],self.r_mitosis_R2[self.transition_counter],self.r_mitosis_R3[self.transition_counter]]
         self.r_grow_list=[self.r_grow_R0[self.transition_counter],self.r_grow_R1[self.transition_counter],self.r_grow_R2[self.transition_counter],self.r_grow_R3[self.transition_counter]]      
         self.transition_counter+=1

      mitosis_list=self.make_mitosis_list()
      self.perform_mitosis(mitosis_list)
      self.y_EN_pos=self.find_posterior_EN_stripe()
      self.y_EN_ant=self.find_anterior_EN_stripe()
      self.y_GZ_border=self.find_y_GZ_mitosis_border()
      for cell in self.cellList:
         self.assign_cell_region(cell)
         self.grow_cell(cell)

class RegionalMitosisWithAPConstraint(ElongationMitosisSteppableBase):

   def __init__(self,_simulator,_frequency, _params_container, _stats_reporter,_OGPlugin):
       ElongationMitosisSteppableBase.__init__(self, _simulator, _frequency, _params_container, _stats_reporter)
       self.OGPlugin = _OGPlugin
      
   def start(self):
      self.y_EN_pos=self.find_posterior_EN_stripe()
      self.y_EN_ant=self.find_anterior_EN_stripe()
      self.y_GZ_border=self.find_y_GZ_mitosis_border()
      for cell in self.cellList:
         region=self.assign_cell_region(cell)
         # self.initiate_cell_volume(cell)  ## Initiates cells with new volumes to distribute mitoses in time
         cellDict = CompuCell.getPyAttrib(cell)
         cellDict['growth_timer']=self.attach_growth_timer(cell)  ## attached a countdown timer for cell growth
         cellDict['divided']=0
         cellDict['divided_GZ']=0
   
   def step(self,mcs):
      self.mcs = mcs
      print 'Executing Mitosis Steppable'
      if mcs in self.transition_times:
         print '*******************TRANSITIONING MITOSIS TIME WINDOW**********************'
         self.reporter.printLn( '*******************TRANSITIONING MITOSIS TIME WINDOW**********************')
         self.r_mitosis_list=[self.r_mitosis_R0[self.transition_counter],self.r_mitosis_R1[self.transition_counter],self.r_mitosis_R2[self.transition_counter],self.r_mitosis_R3[self.transition_counter]]
         self.r_grow_list=[self.r_grow_R0[self.transition_counter],self.r_grow_R1[self.transition_counter],self.r_grow_R2[self.transition_counter],self.r_grow_R3[self.transition_counter]]      
         self.transition_counter+=1

      self.y_EN_pos=self.find_posterior_EN_stripe()
      self.y_EN_ant=self.find_anterior_EN_stripe()
      self.y_GZ_border=self.find_y_GZ_mitosis_border()
      for cell in self.cellList:
         self.assign_cell_region(cell)
         self.grow_cell(cell)
      mitosis_list=self.make_mitosis_list()
      self.perform_mitosis(mitosis_list)

   def updateAttributes(self):
      ElongationMitosisSteppableBase.updateAttributes(self)
      # Attach the elongation constraint to the child cell
      childCell = self.mitosisSteppable.childCell
      self.OGPlugin.setElongationAxis(childCell, 0, 1) # Here, we define the axis of elongation.
      self.OGPlugin.setConstraintWidth(childCell, 4.0) # And this function gives a width constraint to each cell
      self.OGPlugin.setElongationEnabled(childCell, True) # Make sure to enable or disable elongation in all cells
                                                            # Or unexpected results may occur.
           
class InitializeRegionsWithoutMitosis(ElongationMitosisSteppableBase):

   def __init__(self,_simulator,_frequency, _params_container, _stats_reporter):
      ElongationMitosisSteppableBase.__init__(self,_simulator,_frequency, _params_container, _stats_reporter)
      self.y_GZ_mitosis_border_percent = 0

      self.y_EN_pos = None
      self.y_EN_ant = None
      self.y_GZ_border = None
      
   def start(self):
      self.y_EN_pos=self.find_posterior_EN_stripe()
      self.y_EN_ant=self.find_anterior_EN_stripe()
      self.y_GZ_border=self.find_y_GZ_mitosis_border()
      for cell in self.cellList:
         #region=self.assign_cell_region(cell)
         self.assign_cell_region(cell)
         cellDict = CompuCell.getPyAttrib(cell)
         cellDict['divided']=0
         cellDict['divided_GZ']=0
   
   def step(self,mcs):

      self.y_EN_pos=self.find_posterior_EN_stripe()
      self.y_EN_ant=self.find_anterior_EN_stripe()
      self.y_GZ_border=self.find_y_GZ_mitosis_border()
      for cell in self.cellList:
         self.assign_cell_region(cell)
