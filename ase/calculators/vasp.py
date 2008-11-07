# Copyright (C) 2008 CSC - Scientific Computing Ltd.
"""This module defines an ASE interface to VASP.

Developed on the basis of modules by Jussi Enkovaara and John
Kitchin.  The path of the directories of the pseudopotentials (potpaw,
potpaw_GGA, potpaw_PBE, ...) should be set by the environmental flag
$VASP_PP_PATH. 

The user should also set the environmental flag $VASP_SCRIPT pointing to a python script looking something like:
   import os
   exitcode = os.system('vasp')

http://cms.mpi.univie.ac.at/vasp/

-Jonas Bjork j.bjork@liverpool.ac.uk
"""

import os
import sys
from os.path import join, isfile, islink

import numpy as np

import ase

keys = [
    'prec',       # Precission of calculation (Low, Normal, Accurate)
    'nbands',     # Number of bands
    'encut',      # Planewave cutoff
    'enaug',      # Density cutoff
    'ngx',        # FFT mesh for wavefunctions, x
    'ngy',        # FFT mesh for wavefunctions, y
    'ngz',        # FFT mesh for wavefunctions, z
    'ngxf',       # FFT mesh for charges x
    'ngyf',       # FFT mesh for charges y
    'ngzf',       # FFT mesh for charges z
    'nblk',       # blocking for some BLAS calls (Sec. 6.5)
    'system',     # name of System
    'nwrite',     # verbosity write-flag (how much is written)
    'istart',     # startjob: 0-new 1-cont 2-samecut
    'icharg',     # charge: 1-file 2-atom 10-const
    'iniwav',     # initial electr wf. : 0-lowe 1-rand
    'nelm',       #
    'nbands',     #
    'nelmdl',     # nr. of electronic steps
    'ediff',      # stopping-criterion for electronic upd.
    'ediffg',     # stopping-criterion for ionic upd.
    'nsw',        # number of steps for ionic upd.
    'ibrion',     # ionic relaxation: 0-MD 1-quasi-New 2-CG
    'isif',       # calculate stress and what to relax
    'iwavpr',     # prediction of wf.: 0-non 1-charg 2-wave 3-comb
    'isym',       # symmetry: 0-nonsym 1-usesym
    'symprec',    # precession in symmetry routines
    'lcorr',      # Harris-correction to forces
    'potim',      # time-step for ion-motion (fs)
    'tebeg',      #
    'teend',      # temperature during run
    'smass',      # Nose mass-parameter (am)
    'pomass',     # mass of ions in am
    'zval',       # ionic valence
    'rwigs',      # Wigner-Seitz radii
    'nelect',     # total number of electrons
    'nupdown',    # fix spin moment to specified value
    'emin',       #
    'emax',       # energy-range for DOSCAR file
    'ismear',     # part. occupancies: -5 Blochl -4-tet -1-fermi 0-gaus >0 MP
    'sigma',      # broadening in eV -4-tet -1-fermi 0-gaus
    'algo',       # algorithm: Normal (Davidson) | Fast | Very_Fast (RMM-DIIS)
    'ialgo',      # algorithm: use only 8 (CG) or 48 (RMM-DIIS)
    'lreal',      # non-local projectors in real space
    'ropt',       # number of grid points for non-local proj in real space
    'gga',        # xc-type: PW PB LM or 91
    'voskown',    # use Vosko, Wilk, Nusair interpolation
    'dipol',      # center of cell for dipol
    'idipol',     # monopol/dipol and quadropole corrections
    'ldipol',     # potential correction mode
    'amix',       #
    'bmix',       # tags for mixing
    'time',       # special control tag
    'lwave',      #
    'lcharg',     #
    'lvtot',      # create WAVECAR/CHGCAR/LOCPOT
    'lelf',       # create ELFCAR
    'lorbit',     # create PROOUT
    'npar',       # parallelization over bands
    'lscalapack', # switch off scaLAPACK
    'lscalu',     # switch of LU decomposition
    'lasync',     # overlap communcation with calculations
    'addgrid',    # finer grid for augmentation charge density
    'lplane',     # parallelisation over the FFT grid
    'lpard',      # evaluate partial (band and/or k-point) decomposed charge density
    'iband',      # bands to calculate partial charge for
    'eint',       # energy range to calculate partial charge for
    'nbmod',      # specifies mode for partial charge calculation
    'kpuse',      # k-point to calculate partial charge for
    'lsepb',      # write out partial charge of each band seperately?
    'lsepk',      # write out partial charge of each k-point seperately?
    # 'NBLOCK' and KBLOCK       inner block; outer block
    # 'NPACO' and APACO         distance and nr. of slots for P.C.
    # 'WEIMIN, EBREAK, DEPER    special control tags
]

class Vasp:
    def __init__(self, restart=None, **kwargs):

        # Parameters that can be set in INCAR. The values which are None
        # are not written and default parameters of VASP are used for them.
        self.incar_parameters = {}
        for key in keys:
            self.incar_parameters[key] = None
        self.incar_parameters['prec'] = 'Normal'

        self.input_parameters = {
            'xc':     'PW91',  # exchange correlation potential 
            'setups': None,    # Special setups (e.g pv, sv, ...)
            'txt':    '-',     # Where to send information
            'kpts':   (1,1,1), # k-points
            'gamma':  False,   # Option to use gamma-sampling instead
                               # of Monkhorst-Pack
            }

        self.restart = restart
        if restart:
            self.atoms = ase.io.read('CONTCAR', format='vasp')
            self.positions = self.atoms.get_positions()
            self.sort = range(len(self.atoms))
            self.resort = range(len(self.atoms))
            self.read_incar()
            self.read_outcar()
            self.read_kpoints()
            self.old_incar_parameters = self.incar_parameters.copy()
            self.old_input_parameters = self.input_parameters.copy()
            # Set self.converged to True at the moment, this needs to be changed so it checks in the OUTCAR
            # file if the calculation has converged.
            self.converged = self.read_convergence()
            return

        if self.input_parameters['xc'] not in ['PW91','LDA','PBE']:
            raise ValueError(
                '%s not supported for xc! use one of: PW91, LDA or PBE.' %
                kwargs['xc'])
        self.positions = None
        self.nbands = self.incar_parameters['nbands']
        self.atoms = None
        self.set(**kwargs)

    def set(self, **kwargs):
        for key in kwargs:
            if self.input_parameters.has_key(key):
                self.input_parameters[key] = kwargs[key]
            elif self.incar_parameters.has_key(key):
                self.incar_parameters[key] = kwargs[key]
            else:
                raise TypeError('Parameter not defined: ' + key)

    def update(self, atoms):
        if (self.positions is None or
            (self.positions != atoms.get_positions()).any() or
            (self.incar_parameters != self.old_incar_parameters) or
            (self.input_parameters != self.old_input_parameters) or
            not self.converged
            ):
            self.initialize(atoms)
            self.calculate(atoms)

    def initialize(self, atoms):
        """Initialize a VASP calculation

        Constructs the POTCAR file. User should specify the PATH
        to the pseudopotentials in VASP_PP_PATH environment variable"""

        p = self.input_parameters

        self.all_symbols = atoms.get_chemical_symbols()
        self.natoms = len(atoms)
        self.spinpol = atoms.get_initial_magnetic_moments().any()
        #if self.spinpol == False:
           
        # Determine the number of atoms of each atomic species
        # sorted after atomic species

        self.symbols = {}
        for atom in atoms:
            symbol = atom.get_symbol()
            if not self.symbols.has_key(symbol):
                self.symbols[symbol] = 1
            else:
                self.symbols[symbol] += 1
        self.sort = []
        atomtypes = atoms.get_chemical_symbols()
        for symbol in self.symbols:
            for m in range(len(atoms)):
                if atoms[m].get_symbol() == symbol:
                    self.sort.append(m)
        self.resort = range(len(self.sort))
        for n in range(len(self.resort)):
            self.resort[self.sort[n]] = n
        self.atoms_sorted = atoms[self.sort]

        # Check is the necessary POTCAR files exists and
        # create a list of their paths.
        xc = '/'
        print 'p[xc]',p['xc']
        if p['xc'] == 'PW91':
            xc = '_gga/'
        elif p['xc'] == 'PBE':
            xc = '_pbe/'
        if 'VASP_PP_PATH' in os.environ:
            pppaths = os.environ['VASP_PP_PATH'].split(':')
        else:
            pppaths = []
        self.ppp_list = []
        for symbol in self.symbols:
            try:
                name = 'potpaw'+xc.upper()+symbol + p['setups'][symbol]
            except (TypeError, KeyError):
                name = 'potpaw' + xc.upper() + symbol
            name += '/POTCAR'
            found = False
            for path in pppaths:
                filename = join(path, name)
                print 'filename', filename
                if isfile(filename) or islink(filename):
                    found = True
                    self.ppp_list.append(filename)
                    break
                elif isfile(filename + '.Z') or islink(filename + '.Z'):
                    found = True
                    self.ppp_list.append(filename+'.Z')
                    break
            if not found:
                raise RuntimeError('No pseudopotential for %s!' % symbol)
        self.converged = None
        self.setups_changed = None

    def calculate(self, atoms):
        """Generate necessary files in the working directory.
        
        If the directory does not exist it will be created.
        """
        positions = atoms.get_positions()
        ase.io.write('POSCAR', self.atoms_sorted, format='vasp')
        self.write_incar(atoms)
        self.write_potcar()
        self.write_kpoints()

        stderr = sys.stderr
        p=self.input_parameters
        if p['txt'] is None:
            sys.stderr = devnull
        elif p['txt'] == '-':
            pass
        elif isinstance(p['txt'], str):
            sys.stderr = open(p['txt'], 'w')

        vasp = os.environ['VASP_SCRIPT']
        locals={}
        execfile(vasp, {}, locals)
        exitcode = locals['exitcode']
        sys.stderr = stderr
        if exitcode != 0:
            raise RuntimeError('Vasp exited with exit code: %d.  ' % exitcode)

        atoms_sorted = ase.io.read('CONTCAR', format='vasp')
        atoms.set_positions(atoms_sorted.get_positions()[self.resort])
        positions = atoms.get_positions()
        self.positions = positions.copy(atoms)
        self.energy_free, self.energy_zero = self.read_energy()
        self.forces = self.read_forces(atoms)
        self.dipole = self.read_dipole()
        self.fermi = self.read_fermi()
        self.atoms = atoms.copy()
        if not self.nbands:
            self.nbands = self.read_nbands()
        p=self.incar_parameters
        if self.spinpol:
            self.magnetic_moment = self.read_magnetic_moment()
            if p['lorbit']>=10 or (p['lorbit']!=None and p['rwigs']):
                self.magnetic_moments = self.read_magnetic_moments(atoms)
        self.set(nbands=self.nbands)
        self.old_incar_parameters = self.incar_parameters.copy()
        self.old_input_parameters = self.input_parameters.copy()
        self.converged = self.read_convergence()

    def clean(self):
        """Method which cleans up after a calculation.
        
        The default files generated by Vasp will be deleted IF this
        method is called.
        
        """
        files = ['CHG', 'CHGCAR', 'POSCAR', 'INCAR', 'CONTCAR', 'DOSCAR',
                 'EIGENVAL', 'IBZKPT', 'KPOINTS', 'OSZICAR', 'OUTCAR', 'PCDAT',
                 'POTCAR', 'vasprun.xml', 'WAVECAR', 'XDATCAR']
        for f in files:
            try:
                os.remove(f)
            except OSError:
                pass

    def set_atoms(self, atoms):
        self.atoms = atoms.copy()

    def get_atoms(self):
        atoms = self.atoms.copy()
        atoms.set_calculator(self)
        return atoms

    def get_potential_energy(self, atoms, force_consistent=False):
        self.update(atoms)
        if force_consistent:
            return self.energy_free
        else:
            return self.energy_zero

    def get_forces(self, atoms):
        self.update(atoms)
        return self.forces

    def get_stress(self, atoms):
        raise NotImplementedError

    def calculation_required(self,atoms, quantities):
        raise NotImplementedError

    def get_number_of_bands(self):
        return self.nbands

    def get_k_point_weights(self):
        self.update(self.atoms)
        return self.read_k_point_weights()

    def get_number_of_spins(self):
        return 1 + int(self.spinpol)

    def get_eigenvalues(self, kpt=0, spin=0):
        self.update(self.atoms)
        return self.read_eigenvalues(kpt, spin)

    def get_fermi_level(self):
        return self.fermi

    def get_number_of_grid_points(self):
        raise NotImplementedError

    def get_pseudo_density(self):
        raise NotImplementedError

    def get_pseudo_wavefunction(self, n=0, k=0, s=0, pad=True):
        raise NotImplementedError

    def get_bz_k_points(self):
        raise NotImplementedError

    def get_ibz_kpoints(self):
        self.update(self.atoms)
        return self.read_ibz_kpoints()

    def get_spin_polarized(self):
        if not hasattr(self, 'spinpol'):
            self.spinpol = self.atoms.get_initial_magnetic_moments().any()
        return self.spinpol            

    def get_magnetic_moment(self, atoms):
        self.update(atoms)
        return self.magnetic_moment
        
    def get_magnetic_moments(self, atoms):
        p=self.incar_parameters
        if p['lorbit']>=10 or (p['lorbit']!=None and p['rwigs']):
            self.update(atoms)
            return self.magnetic_moments
        else:
            raise RuntimeError(
                "The combination %s for lorbit with %s for rwigs not supported to calculate magnetic moments" % (p['lorbit'], p['rwigs']))

    def get_dipole_moment(self, atoms):
        """Returns total dipole moment of the system."""
        self.update(atoms)
        return self.dipole

    def get_number_of_bands(self):
        return self._nbands

    def write_incar(self, atoms, **kwargs):
        p = self.incar_parameters
        incar = open('INCAR', 'w')
        incar.write('INCAR created by Atomic Simulation Environment\n')
        for key, val in p.items():
            if val is not None:
                incar.write(' '+key.upper()+' = ')
                # special cases:
                if key in ('dipol', 'eint'):
                    [incar.write('%.4f ' % x) for x in val]
                elif key in ('iband', 'nbmod', 'kpuse'):
                    [incar.write('%i ' % x) for x in val]
                elif key == 'rwigs':
                    [incar.write('%.4f ' % rwigs) for rwigs in val]
                    if len(val) != self.natoms:
                        raise RuntimeError('Incorrect number of magnetic moments')
                else:
                    if type(val)==type(bool()):
                        if val:
                            incar.write('.TRUE.')
                        else:
                            incar.write('.FALSE.')
                    else:
                        incar.write('%s' % p[key])
                incar.write('\n')
        if self.spinpol:
            incar.write(' ispin = 2\n'.upper())
            # Write out initial magnetic moments
            magmom = atoms.get_initial_magnetic_moments()[self.sort]
            list = [[1, magmom[0]]]
            for n in range(1, len(magmom)):
                if magmom[n] == magmom[n-1]:
                    list[-1][0] += 1
                else:
                    list.append([1, magmom[n]])
            incar.write(' magmom = '.upper())
            [incar.write('%i*%.4f ' % (mom[0], mom[1])) for mom in list]
            incar.write('\n')
        incar.close()

    def write_kpoints(self, **kwargs):
        p = self.input_parameters
        kpoints = open('KPOINTS', 'w')
        kpoints.write('KPOINTS created by Atomic Simulation Environemnt\n')
        shape=np.array(p['kpts']).shape
        if len(shape)==1:
            kpoints.write('0\n')
            if p['gamma']:
                kpoints.write('Gamma\n')
            else:
                kpoints.write('Monkhorst-Pack\n')
            [kpoints.write('%i ' % kpt) for kpt in p['kpts']]
            kpoints.write('\n0 0 0')
        elif len(shape)==2:
            kpoints.write('%i \n' % (len(p['kpts'])))
            kpoints.write('Cartesian\n')
            for n in range(len(p['kpts'])):
                [kpoints.write('%f ' % kpt) for kpt in p['kpts'][n]]
                if shape[1]==4:
                    kpoints.write('\n')
                elif shape[1]==3:
                    kpoints.write('1.0 \n')
        kpoints.close()

    def write_potcar(self):
        """Write the POTCAR file."""
        import tempfile
        potfile = open('POTCAR','w')
        for filename in self.ppp_list:
            if filename.endswith('R'):
                for line in open(filename, 'r'):
                    potfile.write(line)
            elif filename.endswith('.Z'):
                file_tmp = tempfile.NamedTemporaryFile()
                os.system('gunzip -c %s > %s' % (filename, file_tmp.name))
                for line in file_tmp.readlines():
                    potfile.write(line)
                file_tmp.close()
        potfile.close()

    # Methods for reading information from OUTCAR files:
    def read_energy(self, all=None):
        [energy_free, energy_zero]=[0, 0]
        if all:
            energy_free = []
            energy_zero = []
        for line in open('OUTCAR', 'r'):
            # Free energy
            if line.startswith('  free energy    toten'):
                if all:
                    energy_free.append(float(line.split()[-2]))
                else:
                    energy_free = float(line.split()[-2])
            # Extrapolated zero point energy
            if line.startswith('  energy without entropy'):
                if all:
                    energy_zero.append(float(line.split()[-1]))
                else:
                    energy_zero = float(line.split()[-1])
        return [energy_free, energy_zero]

    def read_forces(self, atoms, all=False):
        """Method that reads forces from OUTCAR file.

        If 'all' is switched on, the forces for all ionic steps
        in the OUTCAR file be returned, in other case only the
        forces for the last ionic configuration is returned."""

        file = open('OUTCAR','r')
        lines = file.readlines()
        file.close()
        n=0
        if all:
            all_forces = []
        for line in lines:
            if line.rfind('TOTAL-FORCE') > -1:
                forces=[]
                for i in range(len(atoms)):
                    forces.append(np.array([float(f) for f in lines[n+2+i].split()[3:6]]))
                if all:
                    all_forces.append(np.array(forces)[self.resort])
            n+=1
        if all:
            return np.array(all_forces)
        else:
            return np.array(forces)[self.resort]

    def read_fermi(self):
        """Method that reads Fermi energy from OUTCAR file"""
        E_f=None
        for line in open('OUTCAR', 'r'):
            if line.rfind('E-fermi') > -1:
                E_f=float(line.split()[2])
        return E_f

    def read_dipole(self):
        dipolemoment=np.zeros([1,3])
        for line in open('OUTCAR', 'r'):
            if line.rfind('dipolmoment') > -1:
                dipolemoment=np.array([float(f) for f in line.split()[1:4]])
        return dipolemoment

    def read_magnetic_moments(self,atoms):
        file = open('OUTCAR', 'r')
        lines = file.readlines()
        file.close
        magnetic_moments=np.zeros(len(atoms))
        n=0
        for line in lines:
            if line.rfind('magnetization (x)') > -1:
                for m in range(0,len(atoms)):
                    magnetic_moments[m]=float(lines[n+m+4].split()[4])
            n+=1
        return np.array(magnetic_moments)[self.resort]

    def read_magnetic_moment(self):
        n=0
        for line in open('OUTCAR','r'):
            if line.rfind('number of electron  ') > -1:
                magnetic_moment=float(line.split()[-1])
            n+=1
        return magnetic_moment

    def read_nbands(self):
        for line in open('OUTCAR', 'r'):
            if line.rfind('NBANDS')>-1:
                return int(line.split()[-1])

    def read_convergence(self):
        """Method that checks whether a calculation has converged."""
        converged = None
        for line in open('OUTCAR', 'r'):
            if line.rfind('EDIFF  ')>-1:
                ediff = float(line.split()[2])
            if line.rfind('total energy-change')>-1:
                split = line.split(':')
                a = float(split[1].split('(')[0])
                b = float(split[1].split('(')[1][0:-2])
                if [abs(a), abs(b)]<[ediff, ediff]:
                    converged = True
                else:
                    converged = None
        return converged

    def read_ibz_kpoints(self):
        lines = open('OUTCAR', 'r').readlines()
        ibz_kpts = []
        n = 0
        i = 0
        for line in lines:
            if line.rfind('Following cartesian coordinates')>-1:
                m = n+2
                while i==0:
                    ibz_kpts.append([float(lines[m].split()[p]) for p in range(3)])
                    m += 1
                    if lines[m]==' \n':
                        i = 1
            if i == 1:
                continue
            n += 1
        ibz_kpts = np.array(ibz_kpts)
        return np.array(ibz_kpts)

    def read_k_point_weights(self):
        file = open('IBZKPT')
        lines = file.readlines()
        file.close()
        kpt_weights = []
        for n in range(3, len(lines)):
            kpt_weights.append(float(lines[n].split()[3]))
        kpt_weights = np.array(kpt_weights)
        kpt_weights /= np.sum(kpt_weights)
        return kpt_weights

    def read_eigenvalues(self, kpt=0, spin=0):
        file = open('EIGENVAL', 'r')
        lines = file.readlines()
        file.close()
        eigs = []
        for n in range(8+kpt*(self.nbands+2), 8+kpt*(self.nbands+2)+self.nbands):
            eigs.append(float(lines[n].split()[spin+1]))
        return np.array(eigs)

# The below functions are used to restart a calculation and are under early constructions

    def read_incar(self):
        file=open('INCAR', 'r')
        file.readline()
        lines=file.readlines()
        for line in lines:
            key = line.split()[0].lower()
            try:
                if key in ['ispin', 'magmom']:
                    continue
                self.incar_parameters[key]
                if key=='dipol':
                    dipol=[]
                    for n in range(3):
                        dipol.append(float(line.split()[n+2]))
                    self.incar_parameters[key] = dipol
                elif key!='':
                    try:
                        self.incar_parameters[key] = int(line.split()[2])
                    except ValueError:
                        try:
                            self.incar_parameters[key] = float(line.split()[2])
                        except ValueError:
                            self.incar_parameters[key] = line.split()[2]
                    self.incar_parameters[key]=line.split()[2]
            except KeyError:
                continue

    def read_outcar(self):
        # Spin polarized calculation?
        file = open('OUTCAR', 'r')
        lines = file.readlines()
        file.close()
        for line in lines:
            if line.rfind('ISPIN') > -1:
                if int(line.split()[2])==2:
                    self.spinpol = True
                else:
                    self.spinpol = None
        self.energy_free, self.energy_zero = self.read_energy()
        self.forces = self.read_forces(self.atoms)
        self.dipole = self.read_dipole()
        self.fermi = self.read_fermi()
        self.nbands = self.read_nbands()
        p=self.incar_parameters
        if self.spinpol:
            self.magnetic_moment = self.read_magnetic_moment()
            if p['lorbit']>=10 or (p['lorbit']!=None and p['rwigs']):
                self.magnetic_moments = self.read_magnetic_moments(self.atoms)
        self.set(nbands=self.nbands)

    def read_kpoints(self):
        file = open('KPOINTS', 'r')
        lines = file.readlines()
        file.close()
        type = lines[2].split()[0].lower()[0]
        if type in ['g', 'm']:
            if type=='g':
                self.set(gamma=True)
            kpts = np.array([int(lines[3].split()[i]) for i in range(3)])
        elif type in ['c', 'k']:
            raise NotImplementedError('Only Monkhorst-Pack and gamma centered grid supported for restart.')
        else:
            raise NotImplementedError('Only Monkhorst-Pack and gamma centered grid supported for restart.')

    def read_charge_density(self, filename='CHG'):
        """Read CHG or CHGCAR file.
        
        TODO: If CHG contains charge density from multiple steps, only
        the first step is read. We should read all the steps, or only
        the last one.
        
        """
        import ase.io.vasp as aiv
        f = open(filename)
        atoms = aiv.read_vasp(f)
        f.readline()
        ng = f.readline().split()
        ng = (int(ng[0]), int(ng[1]), int(ng[2]))
        chg = np.empty(ng)
        # VASP writes charge density as
        # WRITE(IU,FORM) (((C(NX,NY,NZ),NX=1,NGXC),NY=1,NGYZ),NZ=1,NGZC)
        # Fortran nested implied do loops; innermost index fastest
        # First, just read it in
        for zz in range(chg.shape[2]):
            for yy in range(chg.shape[1]):
                chg[:, yy, zz] = np.fromfile(f, count = \
                        chg.shape[0], sep=' ')
        f.close()
        chg /= atoms.get_volume()
        return chg


import pickle

class xdat2traj:
    def __init__(self, trajectory=None, atoms=None, poscar=None, 
                 xdatcar=None, sort=None, calc=None):
        if not poscar:
            self.poscar = 'POSCAR'
        else:
            self.poscar = poscar
        if not atoms:
            self.atoms = ase.io.read(self.poscar, format='vasp')
        else:
            self.atoms = atoms
        if not xdatcar:
            self.xdatcar = 'XDATCAR'
        else:
            self.xdatcar = xdatcar
        if not trajectory:
            self.trajectory = 'out.traj'
        else:
            self.trajectory = trajectory
        if not calc:
            self.calc = Vasp()
        else:
            self.calc = calc
        if not sort: 
            if not hasattr(self.calc, 'sort'):
                self.calc.sort = range(len(self.atoms))
        else:
            self.calc.sort = sort
        self.calc.resort = range(len(self.calc.sort))
        for n in range(len(self.calc.resort)):
            self.calc.resort[self.calc.sort[n]] = n
        self.out = ase.io.trajectory.PickleTrajectory(self.trajectory, mode='w')
        self.energies = self.calc.read_energy(all=True)[1]
        self.forces = self.calc.read_forces(self.atoms, all=True)

    def convert(self):
        lines = open(self.xdatcar).readlines()

        del(lines[0:6])
        step = 0
        iatom = 0
        scaled_pos = []
        for line in lines:
            if iatom == len(self.atoms):
                if step == 0:
                    self.out.write_header(self.atoms[self.calc.resort])
                scaled_pos = np.array(scaled_pos)
                self.atoms.set_scaled_positions(scaled_pos)
                d = {'positions': self.atoms.get_positions()[self.calc.resort],
                     'cell': self.atoms.get_cell(),
                     'momenta': None,
                     'energy': self.energies[step],
                     'forces': self.forces[step],
                     'stress': None}
                pickle.dump(d, self.out.fd, protocol=-1)
                scaled_pos = []
                iatom = 0
                step += 1
            else:
                
                iatom += 1
                scaled_pos.append([float(line.split()[n]) for n in range(3)])
        self.out.fd.close()
