//Core-shell form factor for anisotropy field (Hkx, Hky and Hkz), Nuc and lonitudinal magnetization Mz
static double
form_volume(double radius, double thickness)
{
 return M_4PI_3 * cube(radius + thickness);
}

static double
radius_effective(int mode, double radius, double thickness)
{
 switch (mode) {
    default:
      case 1: // outer radius
        return radius + thickness;
      case 2: // core radius
        return radius;
 }
}

static double fq(double q, double radius,
 double thickness, double core_sld, double shell_sld, double solvent_sld)
{
 const double form = core_shell_fq(q,
  radius,
  thickness,
  core_sld,
  shell_sld,
  solvent_sld);
 return form;
}


static double reduced_field(double q, double Ms, double Hi,
 double A)
{
  if( Hi > 1.0e-6 ) 
    return Ms / (Hi + 2.0 * A * 4.0 * M_PI / Ms * q * q * 10.0);//q in 10e10 m-1, A in 10e-12 J/m, mu0 in 1e-7 
  else 
    return Ms / (1.0e-6 + 2.0 * A * 4.0 * M_PI / Ms * q * q * 10.0); 
 }

 static double DMI_length(double Ms, double D, double qval)
 {
   return 2.0 * D * 4.0 * M_PI / Ms / Ms * qval ; //q in 10e10 m-1, A in 10e-3 J/m^2, mu0 in 4 M_PI 1e-7 
 }

//Mz is defined as the longitudinal magnetisation component along the magnetic field.
//In the approach to saturation this component is (almost) constant with magnetic 
//field and simplfy reflects the nanoscale variations in the saturation magnetisation
//value in the sample. The misalignment of the magnetisation due to perturbing
//magnetic anisotropy or dipolar magnetic fields in the sample enter Mx and My,
//the two transversal magnetisation components, reacting to a magnetic field.
//The micromagnetic solution for the magnetisation are from Michels et al. PRB 94, 054424 (2016).

static double fqMxreal( double x, double y, double z, double Mz, double Hkx, double Hky, double Hi, double Ms, double A, double D)
{
  const double q=MAG_VEC(x, y, z);  
  const double f = reduced_field(q, Ms, Hi, A)*(Hkx*(1.0+reduced_field(q, Ms, Hi, A)*y*y/q/q)-Ms*Mz*x*z/q/q*(1.0+reduced_field(q, Ms, Hi, A)*DMI_length(Ms, D,q)*DMI_length(Ms, D,q))-Hky*reduced_field(q, Ms, Hi, A)*x*y/q/q)/(1.0+reduced_field(q, Ms, Hi, A)*(x*x+y*y)/q/q-square(reduced_field(q, Ms, Hi, A)*DMI_length(Ms, D,z)));
  return f;
}

static double fqMximag(double x, double y, double z, double Mz, double Hkx, double Hky, double Hi, double Ms, double A, double D)
{
  const double q=MAG_VEC(x, y, z);      
  const double f = -reduced_field(q, Ms, Hi, A)*(Ms*Mz*(1.0+reduced_field(q, Ms, Hi, A))*DMI_length(Ms, D,y)+Hky*reduced_field(q, Ms, Hi, A)*DMI_length(Ms, D,z))/(1.0+reduced_field(q, Ms, Hi, A)*(x*x+y*y)/q/q -square(reduced_field(q, Ms, Hi, A)*DMI_length(Ms, D,z)));
  return f;
}

static double fqMyreal( double x, double y, double z, double Mz, double Hkx, double Hky, double Hi, double Ms, double A, double D)
{
  const double q=MAG_VEC(x, y, z);  
  const double f = reduced_field(q, Ms, Hi, A)*(Hky*(1.0+reduced_field(q, Ms, Hi, A)*x*x/q/q)-Ms*Mz*y*z/q/q*(1.0+reduced_field(q, Ms, Hi, A)*DMI_length(Ms, D,q)*DMI_length(Ms, D,q))-Hkx*reduced_field(q, Ms, Hi, A)*x*y/q/q)/(1.0+reduced_field(q, Ms, Hi, A)*(x*x+y*y)/q/q -square(reduced_field(q, Ms, Hi, A)*DMI_length(Ms, D,z)));
  return f;
}

static double fqMyimag( double x, double y, double z, double Mz, double Hkx, double Hky, double Hi, double Ms, double A, double D)
{
  const double q=MAG_VEC(x, y, z);  
  const double f = reduced_field(q, Ms, Hi, A)*(Ms*Mz*(1.0+reduced_field(q, Ms, Hi, A))*DMI_length(Ms, D,x)-Hkx*reduced_field(q, Ms, Hi, A)*DMI_length(Ms, D,z))/(1.0+reduced_field(q, Ms, Hi, A)*(x*x+y*y)/q/q -square(reduced_field(q, Ms, Hi, A)*DMI_length(Ms, D,z)));
  return f;
}

//calculate 2D from _fq
static double
Iqxy(double qx, double qy, double radius, double thickness,double core_nuc, double shell_nuc, double solvent_nuc, double core_Ms, double shell_Ms, double solvent_Ms, double core_hk,  double Hi, double Ms, double A, double D,  double up_i, double up_f, double alpha, double beta)
{
  const double q=MAG_VEC(qx, qy, 0);    
  if (q > 1.0e-16 ) {
    const double cos_theta=qx/q;
    const double sin_theta=qy/q;

    double qrot[3];
    set_scatvec(qrot,q,cos_theta, sin_theta, alpha, beta);
    // 0=dd.real, 1=dd.imag, 2=uu.real, 3=uu.imag,  4=du.real, 6=du.imag,  7=ud.real, 5=ud.imag
    double weights[8];
    set_weights(up_i, up_f, weights);
   
    double mz=fq(q, radius, thickness, core_Ms, shell_Ms, solvent_Ms);
    double nuc=fq(q, radius, thickness, core_nuc, shell_nuc, solvent_nuc);

    double cos_gamma, sin_gamma;
    double sld[8];
    //loop over random anisotropy axis with isotropic orientation gamma for Hkx and Hky
    //To be modified for textured material see also Weissmueller et al. PRB 63, 214414 (2001)
    double total_F2 = 0.0;
    for (int i=0; i<GAUSS_N ;i++) {
      const double gamma = M_PI * (GAUSS_Z[i] + 1.0); // 0 .. 2 pi
      SINCOS(gamma, sin_gamma, cos_gamma);	
      //Only the core of the defect/particle in the matrix has an effective
      //anisotropy (for simplicity), for the effect of different, more complex
      // spatial profile of the anisotropy see Michels PRB 82, 024433 (2010)
      double Hkx= fq(q, radius, thickness, core_hk, 0, 0)*sin_gamma;
      double Hky= fq(q, radius, thickness, core_hk, 0, 0)*cos_gamma;

      double mxreal=fqMxreal(qrot[0], qrot[1], qrot[2], mz, Hkx, Hky, Hi, Ms, A, D);
      double mximag=fqMximag(qrot[0], qrot[1], qrot[2], mz, Hkx, Hky, Hi, Ms, A, D);
      double myreal=fqMyreal(qrot[0], qrot[1], qrot[2], mz, Hkx, Hky, Hi, Ms, A, D);
      double myimag=fqMyimag(qrot[0], qrot[1], qrot[2], mz, Hkx, Hky, Hi, Ms, A, D);

      mag_sld(qrot[0], qrot[1], qrot[2], mxreal, mximag, myreal, myimag, mz, 0, nuc, sld);
      double form = 0.0;
      for (unsigned int xs=0; xs<8; xs++) {
        if (weights[xs] > 1.0e-8) {
          // Since the cross section weight is significant, set the slds
          // to the effective slds for this cross section, call the
          // kernel, and add according to weight.
          // loop over uu, ud real, du real, dd, ud imag, du imag 
          form += weights[xs]*sld[xs]*sld[xs];
        }
      }
      total_F2 += GAUSS_W[i] * form ;
    }
    return 0.5*1.0e-4*total_F2;
  }  
}

static double
Iq(double q, double radius, double thickness,double core_nuc, double shell_nuc, double solvent_nuc, double core_Ms, double shell_Ms, double solvent_Ms, double core_hk, double Hi, double Ms, double A, double D,  double up_i, double up_f, double alpha, double beta)
{
  // slots to hold sincos function output of the orientation on the detector plane
  double sin_theta, cos_theta; 
  double total_F1D = 0.0;
  for (int j=0; j<GAUSS_N ;j++) {

    const double theta = M_PI * (GAUSS_Z[j] + 1.0); // 0 .. 2 pi
    SINCOS(theta, sin_theta, cos_theta);

    double qrot[3];
    set_scatvec(qrot,q,cos_theta, sin_theta, alpha, beta);
    // 0=dd.real, 1=dd.imag, 2=uu.real, 3=uu.imag,  4=du.real, 5=du.imag,  6=ud.real, 7=ud.imag
    double weights[8];  
    set_weights(up_i, up_f, weights);
   
    double mz=fq(q, radius, thickness, core_Ms, shell_Ms, solvent_Ms);
    double nuc=fq(q, radius, thickness, core_nuc, shell_nuc, solvent_nuc);

    double cos_gamma, sin_gamma;
    double sld[8];

    //loop over random anisotropy axis with isotropic orientation gamma for Hkx and Hky
    //To be modified for textured material see also Weissmueller et al. PRB 63, 214414 (2001)
    double total_F2 = 0.0;
    for (int i=0; i<GAUSS_N ;i++) {
      const double gamma = M_PI * (GAUSS_Z[i] + 1.0); // 0 .. 2 pi
      SINCOS(gamma, sin_gamma, cos_gamma);	
      //Only the core of the defect/particle in the matrix has an effective
      //anisotropy (for simplicity), for the effect of different, more complex
      //spatial profile of the anisotropy see Michels PRB 82, 024433 (2010).
      double Hkx= fq(q, radius, thickness, core_hk, 0, 0)*sin_gamma;
      double Hky= fq(q, radius, thickness, core_hk, 0, 0)*cos_gamma;

      double mxreal=fqMxreal(qrot[0], qrot[1], qrot[2], mz, Hkx, Hky, Hi, Ms, A, D);
      double mximag=fqMximag(qrot[0], qrot[1], qrot[2], mz, Hkx, Hky, Hi, Ms, A, D);
      double myreal=fqMyreal(qrot[0], qrot[1], qrot[2], mz, Hkx, Hky, Hi, Ms, A, D);
      double myimag=fqMyimag(qrot[0], qrot[1], qrot[2], mz, Hkx, Hky, Hi, Ms, A, D);

      mag_sld(qrot[0], qrot[1], qrot[2], mxreal, mximag, myreal, myimag, mz, 0, nuc, sld);
      double form = 0.0;
      for (unsigned int xs=0; xs<8; xs++) {
        if (weights[xs] > 1.0e-8 ) {
          // Since the cross section weight is significant, set the slds
          // to the effective slds for this cross section, call the
          // kernel, and add according to weight.
          // loop over uu, ud real, du real, dd, ud imag, du imag 
          form += weights[xs]*sld[xs]*sld[xs];
        }
      }
      total_F2 += GAUSS_W[i] * form ;
    }
    total_F1D += GAUSS_W[j] * total_F2 ;
  }
  //convert from [1e-12 A-1] to [cm-1]
  return 0.25*1.0e-4*total_F1D;
}






