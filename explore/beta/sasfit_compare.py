from __future__ import division, print_function
# Make sasmodels available on the path
import sys, os
BETA_DIR = os.path.dirname(os.path.realpath(__file__))
SASMODELS_DIR = os.path.dirname(os.path.dirname(BETA_DIR))
sys.path.insert(0, SASMODELS_DIR)

from collections import namedtuple

from matplotlib import pyplot as plt
import numpy as np
from numpy import pi, sin, cos, sqrt, fabs
from numpy.polynomial.legendre import leggauss
from scipy.special import j1 as J1
from numpy import inf
from scipy.special import gammaln  # type: ignore

Theory = namedtuple('Theory', 'Q F1 F2 P S I Seff Ibeta')
Theory.__new__.__defaults__ = (None,) * len(Theory._fields)

#Used to calculate F(q) for the cylinder, sphere, ellipsoid models
def sas_sinx_x(x):
    with np.errstate(all='ignore'):
        retvalue = sin(x)/x
    retvalue[x == 0.] = 1.
    return retvalue

def sas_2J1x_x(x):
    with np.errstate(all='ignore'):
        retvalue = 2*J1(x)/x
    retvalue[x == 0] = 1.
    return retvalue

def sas_3j1x_x(x):
    """return 3*j1(x)/x"""
    retvalue = np.empty_like(x)
    with np.errstate(all='ignore'):
        # GSL bessel_j1 taylor expansion
        index = (x < 0.25)
        y = x[index]**2
        c1 = -1.0/10.0
        c2 =  1.0/280.0
        c3 = -1.0/15120.0
        c4 =  1.0/1330560.0
        c5 = -1.0/172972800.0
        retvalue[index] = 1.0 + y*(c1 + y*(c2 + y*(c3 + y*(c4 + y*c5))))
        index = ~index
        y = x[index]
        retvalue[index] = 3*(sin(y) - y*cos(y))/y**3
    retvalue[x == 0.] = 1.
    return retvalue

#Used to cross check my models with sasview models
def build_model(model_name, q, **pars):
    from sasmodels.core import load_model_info, build_model as build_sasmodel
    from sasmodels.data import empty_data1D
    from sasmodels.direct_model import DirectModel
    model_info = load_model_info(model_name)
    model = build_sasmodel(model_info, dtype='double!')
    data = empty_data1D(q)
    calculator = DirectModel(data, model,cutoff=0)
    calculator.pars = pars.copy()
    calculator.pars.setdefault('background', 1e-3)
    return calculator

#gives the hardsphere structure factor that sasview uses
def _hardsphere_simple(q, radius_effective, volfraction):
    CUTOFFHS=0.05
    if fabs(radius_effective) < 1.E-12:
        HARDSPH=1.0
        return HARDSPH
    X = 1.0/( 1.0 -volfraction)
    D= X*X
    A= (1.+2.*volfraction)*D
    A *=A
    X=fabs(q*radius_effective*2.0)
    if X < 5.E-06:
        HARDSPH=1./A
        return HARDSPH
    X2 =X*X
    B = (1.0 +0.5*volfraction)*D
    B *= B
    B *= -6.*volfraction
    G=0.5*volfraction*A
    if X < CUTOFFHS:
        FF = 8.0*A +6.0*B + 4.0*G + ( -0.8*A -B/1.5 -0.5*G +(A/35. +0.0125*B +0.02*G)*X2)*X2
        HARDSPH= 1./(1. + volfraction*FF )
        return HARDSPH
    X4=X2*X2
    S, C = sin(X), cos(X)
    FF=  (( G*( (4.*X2 -24.)*X*S -(X4 -12.*X2 +24.)*C +24. )/X2 + B*(2.*X*S -(X2-2.)*C -2.) )/X + A*(S-X*C))/X
    HARDSPH= 1./(1. + 24.*volfraction*FF/X2 )
    return HARDSPH

def hardsphere_simple(q, radius_effective, volfraction):
    SQ = [_hardsphere_simple(qk, radius_effective, volfraction) for qk in q]
    return np.array(SQ)

#Used in gaussian quadrature for polydispersity
#returns values and the probability of those values based on gaussian distribution
N_GAUSS = 35
NSIGMA_GAUSS = 3
def gaussian_distribution(center, sigma, lb, ub):
    #3 standard deviations covers approx. 99.7%
    if sigma != 0:
        nsigmas = NSIGMA_GAUSS
        x = np.linspace(center-sigma*nsigmas, center+sigma*nsigmas, num=N_GAUSS)
        x= x[(x >= lb) & (x <= ub)]
        px = np.exp((x-center)**2 / (-2.0 * sigma * sigma))
        return x, px
    else:
        return np.array([center]), np.array([1])

N_SCHULZ = 80
NSIGMA_SCHULZ = 8
def schulz_distribution(center, sigma, lb, ub):
    if sigma != 0:
        nsigmas = NSIGMA_SCHULZ
        x = np.linspace(center-sigma*nsigmas, center+sigma*nsigmas, num=N_SCHULZ)
        x= x[(x >= lb) & (x <= ub)]
        R = x/center
        z = (center/sigma)**2
        arg = z*np.log(z) + (z-1)*np.log(R) - R*z - np.log(center) - gammaln(z)
        px = np.exp(arg)
        return x, px
    else:
        return np.array([center]), np.array([1])

#returns the effective radius used in sasview
def ER_ellipsoid(radius_polar, radius_equatorial):
    ee = np.empty_like(radius_polar)
    if radius_polar > radius_equatorial:
        ee = (radius_polar**2 - radius_equatorial**2)/radius_polar**2
    elif radius_polar < radius_equatorial:
        ee = (radius_equatorial**2 - radius_polar**2) / radius_equatorial**2
    else:
        ee = 2*radius_polar
    if (radius_polar * radius_equatorial != 0):
        bd = 1.0 - ee
        e1 = np.sqrt(ee)
        b1 = 1.0 + np.arcsin(e1) / (e1*np.sqrt(bd))
        bL = (1.0 + e1) / (1.0 - e1)
        b2 = 1.0 + bd / 2 / e1 * np.log(bL)
        delta = 0.75 * b1 * b2
    ddd = np.zeros_like(radius_polar)
    ddd = 2.0*(delta + 1.0)*radius_polar*radius_equatorial**2
    return 0.5*ddd**(1.0 / 3.0)

def ellipsoid_volume(radius_polar,radius_equatorial):
    volume = (4./3.)*pi*radius_polar*radius_equatorial**2
    return volume

# F1 is F(q)
# F2 is F(g)^2
#IQM is I(q) with monodispersity
#IQSM is I(q) with structure factor S(q) and monodispersity
#IQBM is I(q) with Beta Approximation and monodispersity
#SQ is monodisperse approach for structure factor
#SQ_EFF is the effective structure factor from beta approx
def ellipsoid_theta(q, radius_polar, radius_equatorial, sld, sld_solvent,
                    volfraction=0, radius_effective=None):
    #creates values z and corresponding probabilities w from legendre-gauss quadrature
    volume = ellipsoid_volume(radius_polar, radius_equatorial)
    z, w = leggauss(76)
    F1 = np.zeros_like(q)
    F2 = np.zeros_like(q)
    #use a u subsition(u=cos) and then u=(z+1)/2 to change integration from
    #0->2pi with respect to alpha to -1->1 with respect to z, allowing us to use
    #legendre-gauss quadrature
    for k, qk in enumerate(q):
        r = sqrt(radius_equatorial**2*(1-((z+1)/2)**2)+radius_polar**2*((z+1)/2)**2)
        F2i = ((sld-sld_solvent)*volume*sas_3j1x_x(qk*r))**2
        F2[k] = np.sum(w*F2i)
        F1i = (sld-sld_solvent)*volume*sas_3j1x_x(qk*r)
        F1[k] = np.sum(w*F1i)
    #the 1/2 comes from the change of variables mentioned above
    F2 = F2/2.0
    F1 = F1/2.0
    if radius_effective is None:
        radius_effective = ER_ellipsoid(radius_polar,radius_equatorial)
    SQ = hardsphere_simple(q, radius_effective, volfraction)
    SQ_EFF = 1 + F1**2/F2*(SQ - 1)
    IQM = 1e-4*F2/volume
    IQSM = volfraction*IQM*SQ
    IQBM = volfraction*IQM*SQ_EFF
    return Theory(Q=q, F1=F1, F2=F2, P=IQM, S=SQ, I=IQSM, Seff=SQ_EFF, Ibeta=IQBM)

#IQD is I(q) polydispursed, IQSD is I(q)S(q) polydispursed, etc.
#IQBD HAS NOT BEEN CROSS CHECKED AT ALL
def ellipsoid_pe(q, radius_polar, radius_equatorial, sld, sld_solvent,
                 radius_polar_pd=0.1, radius_equatorial_pd=0.1,
                 radius_polar_pd_type='gaussian',
                 radius_equatorial_pd_type='gaussian',
                 volfraction=0, radius_effective=None,
                 background=0, scale=1,
                 norm='sasview'):
    if norm not in ['sasview', 'sasfit', 'yun']:
        raise TypeError("unknown norm "+norm)
    if radius_polar_pd_type == 'gaussian':
        Rp_val, Rp_prob = gaussian_distribution(radius_polar, radius_polar_pd*radius_polar, 0, inf)
    elif radius_polar_pd_type == 'schulz':
        Rp_val, Rp_prob = schulz_distribution(radius_polar, radius_polar_pd*radius_polar, 0, inf)
    if radius_equatorial_pd_type == 'gaussian':
        Re_val, Re_prob = gaussian_distribution(radius_equatorial, radius_equatorial_pd*radius_equatorial, 0, inf)
    elif radius_equatorial_pd_type == 'schulz':
        Re_val, Re_prob = schulz_distribution(radius_equatorial, radius_equatorial_pd*radius_equatorial, 0, inf)
    Normalization = 0
    F1,F2 = np.zeros_like(q), np.zeros_like(q)
    radius_eff = total_weight = 0
    for k, Rpk in enumerate(Rp_val):
        for i, Rei in enumerate(Re_val):
            theory = ellipsoid_theta(q,Rpk,Rei,sld,sld_solvent)
            volume = ellipsoid_volume(Rpk, Rei)
            if norm == 'sasfit':
                Normalization += Rp_prob[k]*Re_prob[i]
            elif norm == 'sasview' or norm == 'yun':
                Normalization += Rp_prob[k]*Re_prob[i]*volume
            F1 += theory.F1*Rp_prob[k]*Re_prob[i]
            F2 += theory.F2*Rp_prob[k]*Re_prob[i]
            radius_eff += Rp_prob[k]*Re_prob[i]*ER_ellipsoid(Rpk,Rei)
            total_weight += Rp_prob[k]*Re_prob[i]
    F1 = F1/Normalization
    F2 = F2/Normalization
    if radius_effective is None:
        radius_effective = radius_eff/total_weight
    SQ = hardsphere_simple(q, radius_effective, volfraction)
    SQ_EFF = 1 + F1**2/F2*(SQ - 1)
    volume = ellipsoid_volume(radius_polar, radius_equatorial)
    if norm == 'sasfit':
        IQD = F2
        IQSD = IQD*SQ
        IQBD = IQD*SQ_EFF
    elif norm == 'sasview':
        IQD = F2*1e-4*volfraction
        IQSD = IQD*SQ
        IQBD = IQD*SQ_EFF
    elif norm == 'yun':
        SQ_EFF = 1 + Normalization*F1**2/F2*(SQ - 1)
        F2 = F2/volume
        IQD = F2
        IQSD = IQD*SQ
        IQBD = IQD*SQ_EFF
    return Theory(Q=q, F1=F1, F2=F2, P=IQD, S=SQ, I=IQSD, Seff=SQ_EFF, Ibeta=IQBD)

#polydispersity for sphere
def sphere_r(q,radius,sld,sld_solvent,
             radius_pd=0.1, radius_pd_type='gaussian',
             volfraction=0, radius_effective=None,
             background=0, scale=1,
             norm='sasview'):
    if norm not in ['sasview', 'sasfit', 'yun']:
        raise TypeError("unknown norm "+norm)
    if radius_pd_type == 'gaussian':
        radius_val, radius_prob = gaussian_distribution(radius, radius_pd*radius, 0, inf)
    elif radius_pd_type == 'schulz':
        radius_val, radius_prob = schulz_distribution(radius, radius_pd*radius, 0, inf)
    Normalization=0
    F1 = np.zeros_like(q)
    F2 = np.zeros_like(q)
    for k, rk in enumerate(radius_val):
        volume = 4./3.*pi*rk**3
        if norm == 'sasfit':
            Normalization += radius_prob[k]
        elif norm == 'sasview' or norm == 'yun':
            Normalization += radius_prob[k]*volume
        F2k = ((sld-sld_solvent)*volume*sas_3j1x_x(q*rk))**2
        F1k = (sld-sld_solvent)*volume*sas_3j1x_x(q*rk)
        F2 += radius_prob[k]*F2k
        F1 += radius_prob[k]*F1k

    F2 = F2/Normalization
    F1 = F1/Normalization
    if radius_effective is None:
        radius_effective = radius
    SQ = hardsphere_simple(q, radius_effective, volfraction)
    SQ_EFF = 1 + F1**2/F2*(SQ - 1)
    volume = 4./3.*pi*radius**3
    if norm == 'sasfit':
        IQD = F2
        IQSD = IQD*SQ
        IQBD = IQD*SQ_EFF
    elif norm == 'sasview':
        IQD = F2*1e-4*volfraction
        IQSD = IQD*SQ
        IQBD = IQD*SQ_EFF
    elif norm == 'yun':
        SQ_EFF = 1 + Normalization*F1**2/F2*(SQ - 1)
        F2 = F2/volume
        IQD = F2
        IQSD = IQD*SQ
        IQBD = IQD*SQ_EFF
    return Theory(Q=q, F1=F1, F2=F2, P=IQD, S=SQ, I=IQSD, Seff=SQ_EFF, Ibeta=IQBD)

###############################################################################
###############################################################################
###############################################################################
##################                                           ##################
##################                   TESTS                   ##################
##################                                           ##################
###############################################################################
###############################################################################
###############################################################################

def popn(d, keys):
    """
    Splits a dict into two, with any key of *d* which is in *keys* removed
    from *d* and added to *b*. Returns *b*.
    """
    b = {}
    for k in keys:
        try:
            b[k] = d.pop(k)
        except KeyError:
            pass
    return b

def sasmodels_theory(q, Pname, **pars):
    """
    Call sasmodels to compute the model with and without a hard sphere
    structure factor.
    """
    #mono_pars = {k: (0 if k.endswith('_pd') else v) for k, v in pars.items()}
    Ppars = pars.copy()
    Spars = popn(Ppars, ['radius_effective', 'volfraction'])
    Ipars = pars.copy()

    # Autofill npts and nsigmas for the given pd type
    for k, v in pars.items():
        if k.endswith("_pd_type"):
            if v == "gaussian":
                n, nsigmas = N_GAUSS, NSIGMA_GAUSS
            elif v == "schulz":
                n, nsigmas = N_SCHULZ, NSIGMA_SCHULZ
            Ppars.setdefault(k.replace("_pd_type", "_pd_n"), n)
            Ppars.setdefault(k.replace("_pd_type", "_pd_nsigma"), nsigmas)
            Ipars.setdefault(k.replace("_pd_type", "_pd_n"), n)
            Ipars.setdefault(k.replace("_pd_type", "_pd_nsigma"), nsigmas)

    #Ppars['scale'] = Spars.get('volfraction', 1)
    P = build_model(Pname, q)
    S = build_model("hardsphere", q)
    I = build_model(Pname+"@hardsphere", q)
    Pq = P(**Ppars)*pars.get('volfraction', 1)
    #Sq = S(**Spars)
    Iq = I(**Ipars)
    #Iq = Pq*Sq*pars.get('volfraction', 1)
    Sq = Iq/Pq
    return Theory(Q=q, F1=None, F2=None, P=Pq, S=Sq, I=Iq, Seff=None, Ibeta=None)

def compare(title, target, actual, fields='F1 F2 P S I Seff Ibeta'):
    """
    Plot fields in common between target and actual, along with relative error.
    """
    available = [s for s in fields.split()
                 if getattr(target, s) is not None and getattr(actual, s) is not None]
    rows = len(available)
    for row, field in enumerate(available):
        Q = target.Q
        I1, I2 = getattr(target, field), getattr(actual, field)
        plt.subplot(rows, 2, 2*row+1)
        plt.loglog(Q, abs(I1), label="target "+field)
        plt.loglog(Q, abs(I2), label="value "+field)
        #plt.legend(loc="upper left", bbox_to_anchor=(1,1))
        plt.legend(loc='lower left')
        plt.subplot(rows, 2, 2*row+2)
        #plt.semilogx(Q, I2/I1 - 1, label="relative error")
        plt.semilogx(Q, I1/I2 - 1, label="relative error")
    plt.tight_layout()
    plt.suptitle(title)
    plt.show()

def data_file(name):
    return os.path.join(BETA_DIR, 'data_files', name)

def load_sasfit(path):
    data = np.loadtxt(path, dtype=str, delimiter=';').T
    data = np.vstack((map(float, v) for v in data[0:2]))
    return data

COMPARISON = {}  # Type: Dict[(str,str,str)] -> Callable[(), None]

def compare_sasview_sphere(pd_type='schulz'):
    q = np.logspace(-5, 0, 250)
    model = 'sphere'
    pars = dict(
        radius=20,sld=4,sld_solvent=1,
        background=0,
        radius_pd=.1, radius_pd_type=pd_type,
        volfraction=0.15,
        #radius_effective=12.59921049894873,  # equivalent average sphere radius
        )
    target = sasmodels_theory(q, model, **pars)
    actual = sphere_r(q, norm='sasview', **pars)
    title = " ".join(("sasmodels", model, pd_type))
    compare(title, target, actual)
COMPARISON[('sasview','sphere','gaussian')] = lambda: compare_sasview_sphere(pd_type='gaussian')
COMPARISON[('sasview','sphere','schulz')] = lambda: compare_sasview_sphere(pd_type='schulz')

def compare_sasview_ellipsoid(pd_type='gaussian'):
    q = np.logspace(-5, 0, 50)
    model = 'ellipsoid'
    pars = dict(
        radius_polar=20,radius_equatorial=400,sld=4,sld_solvent=1,
        background=0,
        radius_polar_pd=.1, radius_polar_pd_type=pd_type,
        radius_equatorial_pd=.1, radius_equatorial_pd_type=pd_type,
        volfraction=0.15,
        #radius_effective=12.59921049894873,
        )
    target = sasmodels_theory(q, model, **pars)
    actual = ellipsoid_pe(q, norm='sasview', **pars)
    title = " ".join(("sasmodels", model, pd_type))
    compare(title, target, actual)
COMPARISON[('sasview','ellipsoid','gaussian')] = lambda: compare_sasview_sphere(pd_type='gaussian')
COMPARISON[('sasview','ellipsoid','schulz')] = lambda: compare_sasview_sphere(pd_type='schulz')

def compare_yun_ellipsoid_mono():
    pars = {
        'radius_polar': 20, 'radius_polar_pd': 0, 'radius_polar_pd_type': 'gaussian',
        'radius_equatorial': 10, 'radius_equatorial_pd': 0, 'radius_equatorial_pd_type': 'gaussian',
        'sld': 2, 'sld_solvent': 1,
        'volfraction': 0.15,
        # Yun uses radius for same volume sphere for effective radius
        # whereas sasview uses the average curvature.
        'radius_effective': 12.59921049894873,
    }
    volume = ellipsoid_volume(pars['radius_polar'], pars['radius_equatorial'])

    data = np.loadtxt(data_file('yun_ellipsoid.dat'),skiprows=2).T
    Q = data[0]
    F1 = data[1]
    F2 = data[3]
    S = data[5]
    Seff = data[6]
    P = F2
    I = P*S
    Ibeta = P*Seff
    P = I = Ibeta = None
    target = Theory(Q=Q, F1=F1, F2=F2, P=P, S=S, I=I, Seff=Seff, Ibeta=Ibeta)
    actual = ellipsoid_pe(Q, norm='yun', **pars)
    title = " ".join(("yun", "ellipsoid", "no pd"))
    #compare(title, target, actual, fields="P S I Seff Ibeta")
    compare(title, target, actual)
COMPARISON[('yun','ellipsoid','gaussian')] = compare_yun_ellipsoid_mono
COMPARISON[('yun','ellipsoid','schulz')] = compare_yun_ellipsoid_mono

def compare_sasfit_sphere_gauss():
    #N=1,s=2,X0=20,distr radius R=20,eta_core=4,eta_solv=1,.3
    pars = {
        'radius': 20, 'radius_pd': 0.1, 'radius_pd_type': 'gaussian',
        'sld': 4, 'sld_solvent': 1,
        'volfraction': 0.3,
    }
    volume = 4./3.*pi*pars['radius']**3
    Q, IQ = load_sasfit(data_file('sasfit_sphere_IQD.txt'))
    Q, IQSD = load_sasfit(data_file('sasfit_sphere_IQSD.txt'))
    Q, IQBD = load_sasfit(data_file('sasfit_sphere_IQBD.txt'))
    Q, SQ = load_sasfit(data_file('sasfit_polydisperse_sphere_sq.txt'))
    Q, SQ_EFF = load_sasfit(data_file('sasfit_polydisperse_sphere_sqeff.txt'))
    target = Theory(Q=Q, F1=None, F2=None, P=IQ, S=SQ, I=IQSD, Seff=SQ_EFF, Ibeta=IQBD)
    actual = sphere_r(Q, norm="sasfit", **pars)
    title = " ".join(("sasfit", "sphere", "pd=10% gaussian"))
    compare(title, target, actual)
    #compare(title, target, actual, fields="P")
COMPARISON[('sasfit','sphere','gaussian')] = compare_sasfit_sphere_gauss

def compare_sasfit_sphere_schulz():
    #radius=20,sld=4,sld_solvent=1,volfraction=0.3,radius_pd=0.1
    #We have scaled the output from sasfit by 1e-4*volume*volfraction
    #0.10050378152592121
    pars = {
        'radius': 20, 'radius_pd': 0.1, 'radius_pd_type': 'schulz',
        'sld': 4, 'sld_solvent': 1,
        'volfraction': 0.3,
    }
    volume = 4./3.*pi*pars['radius']**3

    Q, IQ = load_sasfit(data_file('richard_test.txt'))
    Q, IQSD = load_sasfit(data_file('richard_test2.txt'))
    Q, IQBD = load_sasfit(data_file('richard_test3.txt'))
    target = Theory(Q=Q, F1=None, F2=None, P=IQ, S=None, I=IQSD, Seff=None, Ibeta=IQBD)
    actual = sphere_r(Q, norm="sasfit", **pars)
    title = " ".join(("sasfit", "sphere", "pd=10% schulz"))
    compare(title, target, actual)
COMPARISON[('sasfit','sphere','schulz')] = compare_sasfit_sphere_schulz

def compare_sasfit_ellipsoid_schulz():
    #polarradius=20, equatorialradius=10, sld=4,sld_solvent=1,volfraction=0.3,radius_polar_pd=0.1
    #Effective radius =13.1353356684
    #We have scaled the output from sasfit by 1e-4*volume*volfraction
    #0.10050378152592121
    pars = {
        'radius_polar': 20, 'radius_polar_pd': 0.1, 'radius_polar_pd_type': 'schulz',
        'radius_equatorial': 10, 'radius_equatorial_pd': 0., 'radius_equatorial_pd_type': 'schulz',
        'sld': 4, 'sld_solvent': 1,
        'volfraction': 0.3, 'radius_effective': 13.1353356684,
    }
    volume = ellipsoid_volume(pars['radius_polar'], pars['radius_equatorial'])
    Q, IQ = load_sasfit(data_file('richard_test4.txt'))
    Q, IQSD = load_sasfit(data_file('richard_test5.txt'))
    Q, IQBD = load_sasfit(data_file('richard_test6.txt'))
    target = Theory(Q=Q, F1=None, F2=None, P=IQ, S=None, I=IQSD, Seff=None, Ibeta=IQBD)
    actual = ellipsoid_pe(Q, norm="sasfit", **pars)
    title = " ".join(("sasfit", "ellipsoid", "pd=10% schulz"))
    compare(title, target, actual)
COMPARISON[('sasfit','ellipsoid','schulz')] = compare_sasfit_ellipsoid_schulz


def compare_sasfit_ellipsoid_gaussian():
    pars = {
        'radius_polar': 20, 'radius_polar_pd': 0, 'radius_polar_pd_type': 'gaussian',
        'radius_equatorial': 10, 'radius_equatorial_pd': 0, 'radius_equatorial_pd_type': 'gaussian',
        'sld': 4, 'sld_solvent': 1,
        'volfraction': 0, 'radius_effective': None,
    }

    #Rp=20,Re=10,eta_core=4,eta_solv=1
    Q, PQ0 = load_sasfit(data_file('sasfit_ellipsoid_IQM.txt'))
    pars.update(volfraction=0, radius_polar_pd=0.0, radius_equatorial_pd=0, radius_effective=None)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, P=PQ0)
    compare("sasfit ellipsoid no poly", target, actual); plt.show()

    #N=1,s=2,X0=20,distr 10% polar Rp=20,Re=10,eta_core=4,eta_solv=1, no structure poly
    Q, PQ_Rp10 = load_sasfit(data_file('sasfit_ellipsoid_IQD.txt'))
    pars.update(volfraction=0, radius_polar_pd=0.1, radius_equatorial_pd=0.0, radius_effective=None)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, P=PQ_Rp10)
    compare("sasfit ellipsoid P(Q) 10% Rp", target, actual); plt.show()
    #N=1,s=1,X0=10,distr 10% equatorial Rp=20,Re=10,eta_core=4,eta_solv=1, no structure poly
    Q, PQ_Re10 = load_sasfit(data_file('sasfit_ellipsoid_IQD2.txt'))
    pars.update(volfraction=0, radius_polar_pd=0.0, radius_equatorial_pd=0.1, radius_effective=None)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, P=PQ_Re10)
    compare("sasfit ellipsoid P(Q) 10% Re", target, actual); plt.show()
    #N=1,s=6,X0=20,distr 30% polar Rp=20,Re=10,eta_core=4,eta_solv=1, no structure poly
    Q, PQ_Rp30 = load_sasfit(data_file('sasfit_ellipsoid_IQD3.txt'))
    pars.update(volfraction=0, radius_polar_pd=0.3, radius_equatorial_pd=0.0, radius_effective=None)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, P=PQ_Rp30)
    compare("sasfit ellipsoid P(Q) 30% Rp", target, actual); plt.show()
    #N=1,s=3,X0=10,distr 30% equatorial Rp=20,Re=10,eta_core=4,eta_solv=1, no structure poly
    Q, PQ_Re30 = load_sasfit(data_file('sasfit_ellipsoid_IQD4.txt'))
    pars.update(volfraction=0, radius_polar_pd=0.0, radius_equatorial_pd=0.3, radius_effective=None)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, P=PQ_Re30)
    compare("sasfit ellipsoid P(Q) 30% Re", target, actual); plt.show()
    #N=1,s=12,X0=20,distr 60% polar Rp=20,Re=10,eta_core=4,eta_solv=1, no structure poly
    Q, PQ_Rp60 = load_sasfit(data_file('sasfit_ellipsoid_IQD5.txt'))
    pars.update(volfraction=0, radius_polar_pd=0.6, radius_equatorial_pd=0.0, radius_effective=None)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, P=PQ_Rp60)
    compare("sasfit ellipsoid P(Q) 60% Rp", target, actual); plt.show()
    #N=1,s=6,X0=10,distr 60% equatorial Rp=20,Re=10,eta_core=4,eta_solv=1, no structure poly
    Q, PQ_Re60 = load_sasfit(data_file('sasfit_ellipsoid_IQD6.txt'))
    pars.update(volfraction=0, radius_polar_pd=0.0, radius_equatorial_pd=0.6, radius_effective=None)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, P=PQ_Re60)
    compare("sasfit ellipsoid P(Q) 60% Re", target, actual); plt.show()

    #N=1,s=2,X0=20,distr polar Rp=20,Re=10,eta_core=4,eta_solv=1, hardsphere ,13.1354236254,.15
    Q, SQ = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sq.txt'))
    Q, SQ_EFF = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sqeff.txt'))
    pars.update(volfraction=0.15, radius_polar_pd=0.1, radius_equatorial_pd=0, radius_effective=13.1354236254)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, S=SQ, Seff=SQ_EFF)
    compare("sasfit ellipsoid P(Q) 10% Rp 15% Vf", target, actual); plt.show()
    #N=1,s=6,X0=20,distr polar Rp=20,Re=10,eta_core=4,eta_solv=1, hardsphere ,13.0901197149,.15
    Q, SQ = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sq2.txt'))
    Q, SQ_EFF = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sqeff2.txt'))
    pars.update(volfraction=0.15, radius_polar_pd=0.3, radius_equatorial_pd=0, radius_effective=13.0901197149)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, S=SQ, Seff=SQ_EFF)
    compare("sasfit ellipsoid P(Q) 30% Rp 15% Vf", target, actual); plt.show()
    #N=1,s=12,X0=20,distr polar Rp=20,Re=10,eta_core=4,eta_solv=1, hardsphere ,13.336060917,.15
    Q, SQ = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sq3.txt'))
    Q, SQ_EFF = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sqeff3.txt'))
    pars.update(volfraction=0.15, radius_polar_pd=0.6, radius_equatorial_pd=0, radius_effective=13.336060917)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, S=SQ, Seff=SQ_EFF)
    compare("sasfit ellipsoid P(Q) 60% Rp 15% Vf", target, actual); plt.show()

    #N=1,s=2,X0=20,distr polar Rp=20,Re=10,eta_core=4,eta_solv=1, hardsphere ,13.1354236254,.3
    Q, SQ = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sq4.txt'))
    Q, SQ_EFF = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sqeff4.txt'))
    pars.update(volfraction=0.3, radius_polar_pd=0.1, radius_equatorial_pd=0, radius_effective=13.1354236254)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, S=SQ, Seff=SQ_EFF)
    compare("sasfit ellipsoid P(Q) 10% Rp 30% Vf", target, actual); plt.show()
    #N=1,s=6,X0=20,distr polar Rp=20,Re=10,eta_core=4,eta_solv=1, hardsphere ,13.0901197149,.3
    Q, SQ = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sq5.txt'))
    Q, SQ_EFF = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sqeff5.txt'))
    pars.update(volfraction=0.3, radius_polar_pd=0.3, radius_equatorial_pd=0, radius_effective=13.0901197149)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, S=SQ, Seff=SQ_EFF)
    compare("sasfit ellipsoid P(Q) 30% Rp 30% Vf", target, actual); plt.show()
    #N=1,s=12,X0=20,distr polar Rp=20,Re=10,eta_core=4,eta_solv=1, hardsphere ,13.336060917,.3
    Q, SQ = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sq6.txt'))
    Q, SQ_EFF = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sqeff6.txt'))
    pars.update(volfraction=0.3, radius_polar_pd=0.6, radius_equatorial_pd=0, radius_effective=13.336060917)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, S=SQ, Seff=SQ_EFF)
    compare("sasfit ellipsoid P(Q) 60% Rp 30% Vf", target, actual); plt.show()

    #N=1,s=2,X0=20,distr polar Rp=20,Re=10,eta_core=4,eta_solv=1, hardsphere ,13.1354236254,.6
    Q, SQ = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sq7.txt'))
    Q, SQ_EFF = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sqeff7.txt'))
    pars.update(volfraction=0.6, radius_polar_pd=0.1, radius_equatorial_pd=0, radius_effective=13.1354236254)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, S=SQ, Seff=SQ_EFF)
    compare("sasfit ellipsoid P(Q) 10% Rp 60% Vf", target, actual); plt.show()
    #N=1,s=6,X0=20,distr polar Rp=20,Re=10,eta_core=4,eta_solv=1, hardsphere ,13.0901197149,.6
    Q, SQ = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sq8.txt'))
    Q, SQ_EFF = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sqeff8.txt'))
    pars.update(volfraction=0.6, radius_polar_pd=0.3, radius_equatorial_pd=0, radius_effective=13.0901197149)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, S=SQ, Seff=SQ_EFF)
    compare("sasfit ellipsoid P(Q) 30% Rp 60% Vf", target, actual); plt.show()
    #N=1,s=12,X0=20,distr polar Rp=20,Re=10,eta_core=4,eta_solv=1, hardsphere ,13.336060917,.6
    Q, SQ = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sq9.txt'))
    Q, SQ_EFF = load_sasfit(data_file('sasfit_polydisperse_ellipsoid_sqeff9.txt'))
    pars.update(volfraction=0.6, radius_polar_pd=0.6, radius_equatorial_pd=0, radius_effective=13.336060917)
    actual = ellipsoid_pe(Q, norm='sasfit', **pars)
    target = Theory(Q=Q, S=SQ, Seff=SQ_EFF)
    compare("sasfit ellipsoid P(Q) 60% Rp 60% Vf", target, actual); plt.show()
COMPARISON[('sasfit','ellipsoid','gaussian')] = compare_sasfit_ellipsoid_schulz

def main():
    key = tuple(sys.argv[1:])
    if key not in COMPARISON:
        print("usage: sasfit_compare.py [sasview|sasfit|yun] [sphere|ellipsoid] [gaussian|schulz]")
        return
    comparison = COMPARISON[key]
    comparison()

if __name__ == "__main__":
    main()
