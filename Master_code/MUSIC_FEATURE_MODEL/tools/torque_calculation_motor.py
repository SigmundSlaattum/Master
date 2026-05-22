import numpy as np

# Parameters
m = 100 #kg
g = 9.81 #m/s^2
r = 0.005 #m
f = 2 #Hz for 120 BPM (120/60 = 2)
amplitude = np.pi # radians (half rotation)
r_gear = 15 # gear ratio
n = 0.66 # efficiency
Kv = 192 # rpm/V
Kt = 60 / (2 * np.pi * Kv) # Nm/A
voltage= 32 # Volts

# Anglular frequency
omega = 2 * np.pi * f # rad/s

# Static force due to weight of load
F_static = m * g # N

# Cam angle as a function of time - TODO: Perhaps remove in favor of angle driven and not time
def theta(t):
    return amplitude * np.sin(omega * t)

# ---------------------------- Static and Dynamic load calculations ----------------------------

# Cam angle:
def theta(t):
    return amplitude * np.sin(omega * t)

# Cam Angular velocity:
def theta_dot(t):
    return amplitude * omega * np.cos(omega * t)

# Cam Angular acceleration:
def theta_ddot(t):
    return -amplitude * omega**2 * np.sin(omega * t)


# Vertical position of platform:
def z(t):
    return r*(1-np.cos(theta(t)))

# Vertical velocity of platform:
def z_dot(t):
    return r * np.sin(theta(t)) * theta_dot(t)

# Vertical acceleration of platform:
def z_ddot(t):
    return r * (np.sin(theta(t)) * theta_ddot(t) + np.cos(theta(t)) * theta_dot(t)**2)


# --------------------------- Torque calculations ---------------------------

def F_dynamic(t):
    return m * z_ddot(t) # N

def F_total(t):
    return F_static + F_dynamic(t) # N

def torque_at_cam(t):
    return F_total(t) * r * np.sin(theta(t)) # Nm

def torque_at_motor(t):
    return torque_at_cam(t) / (r_gear * n) # Nm


# ---------------------------- Current, motor power, and bemf calculations ---------------------------

def current(t):
    return torque_at_motor(t) / Kt # A  

def motor_power(t):
    return torque_at_motor(t) * theta_dot(t) * r_gear # W

def back_emf(t):
    return theta_dot(t) * r_gear / Kv # V

# ---------------------------- Sweep calculations ----------------------------

t_values = np.linspace(0, 1/f, 10000)

def angle_of_max_torque():
    max_torque = -np.inf
    max_angle = 0
    for t in t_values:
        torque = torque_at_motor(t)
        if torque > max_torque:
            max_torque = torque
            max_angle = np.degrees(theta(t))
    return max_angle, max_torque

def print_clean_angles_and_torques():
    for deg in range(0, 181):              # every degree, 0..180, once each
        t = np.arcsin(np.radians(deg) / amplitude) / omega   # exact time the cam hits this angle

        angle_deg = np.degrees(theta(t))   # will print back as the integer degree
        print(f"Angle: {angle_deg:7.3f} deg, "
              f"Torque at Motor: {torque_at_motor(t):.3f} Nm, "
              f"Current: {current(t):.3f} A, "
              f"Motor Power: {motor_power(t):.3f} W, "
              f"Back EMF: {back_emf(t):.3f} V")

print_clean_angles_and_torques()
print(f"Angle of max torque: {angle_of_max_torque()[0]:.3f} deg, Max Torque: {angle_of_max_torque()[1]:.3f} Nm at motor")