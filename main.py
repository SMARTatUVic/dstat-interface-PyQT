from PyQt5 import QtGui, QtWidgets, uic, QtCore
import serial, time, datetime, json, worker, struct
from serial.tools import list_ports
import pyqtgraph as pg

class MainWindow(QtWidgets.QMainWindow):

    # Serial object for communication with DStat
    ser = None

    def __init__(self, *args, **kwargs):

        # Load external ui file. Edit this ui file in 'Qt Designer'
        super(MainWindow, self).__init__(*args, **kwargs)
        uic.loadUi('dstat-interface.ui', self)

        self.threadpool = QtCore.QThreadPool()

        # pyQT graph plot objects
        self.exp_data_x = []
        self.exp_data_y = []
        self.exp_line = self.exp_plot.plot()
        self.plot_timer = QtCore.QTimer()
        self.plot_timer.setInterval(int(1000/10))
        self.plot_timer.timeout.connect(self.update_plot)

        # True if DStat is connected via usb
        self.connected = False

        # True if experiment running. Controls exit dialog
        self.experiment_active = False

        self.connect_signals()
        self.refresh_ports()
        self.load_UI_options()
        self.set_UI_visibility("UNCONNECTED")

    # Collect new serial data from the DStat. Runs on a seperate thread.
    def read_serial(self, signals):

        # Note this prints to the status box in an odd way for thread
        # safety between the main event loop and the worker thread.

        file = None
        new_exp = True

        while self.connected:

            # Experiment started. Create new file
            if self.experiment_active == True and new_exp == True:
                new_exp = False

                fmt = "{:%Y-%m-%dT%H-%M-%S}_" + \
                      self.exptype_dropdown.currentText() + ".csv"
                file_name = fmt.format(datetime.datetime.now())
                file = open(file_name, 'w')

                # Header for csv
                match self.exptype_dropdown.currentText():
                    case "Linear Sweep Voltammetry":
                        file.write('voltage [V],current [A]\n')
                    case "Potentiometry":
                        file.write('voltage [V],current [A]\n')
            
            # Experiment ended. Close file
            elif self.experiment_active == False and new_exp == False:
                signals.msg.emit("Exported to: " + file_name)
                new_exp = True
                file.close()
            
            # Process serial data from dstat
            try:
                line = self.ser.readline()
                            
                if line.startswith(b'B'):

                    # Data arrives in binary in "ADC/DAC units"
                    # See communication protocol.txt of dstat-firmware repo

                    match self.exptype_dropdown.currentText():
                        case "Linear Sweep Voltammetry":
                            # voltage, current
                            # uint16 + int32
                            d_size = int(2+4)
                            data = self.ser.read(d_size)
                            V, I = struct.unpack( '<Hl', data)
                            V = self.correct_voltage(V, "Voltammetry")
                            I = self.correct_current(I)

                            self.exp_data_x.insert(0, V)
                            self.exp_data_y.insert(0, I)

                            # Notify for convenience
                            status =  "{:.3e}".format(self.exp_data_x[0])
                            status += ",{:.3e}".format(self.exp_data_y[0])
                            signals.msg.emit(status)
                            file.write(status + '\n')

                        case "Potentiometry":
                            # seconds, milliseconds, voltage
                            # 2*uint16 + int32
                            d_size = int(2+2+4)
                            data = self.ser.read(d_size)
                            s, ms, V = struct.unpack( '<HHl', data)
                            V = self.correct_voltage(V, "Potentiometry")

                            self.exp_data_x.insert(0, s + ms/1000)
                            self.exp_data_y.insert(0, V)

                            # Notify for convenience
                            status =  "{:.1f}".format(self.exp_data_x[0])
                            status += ",{:.5f}".format(self.exp_data_y[0])
                            signals.msg.emit(status)
                            file.write(status + '\n')

                        case _:
                            signals.msg.emit("Error: Unknown experiment type")
                        
                elif line.lstrip().startswith(b"#"):
                    signals.msg.emit(line.lstrip().rstrip().decode("utf-8"))
                        
                elif line.lstrip().startswith(b"@"):
                    line = line.lstrip().rstrip().decode("utf-8")
                    signals.msg.emit(line)

                    match line:
                        case "@DONE":
                            # TODO make this call stop_exp()
                            pass

    
            except serial.SerialException:
                print("SerialException!")
                print(line)

    # Convert a raw ADC/DAC value from DStat to voltage
    def correct_voltage(self, raw, exp_type):

        # PGA gain is 2^(DStat gain setting)
        pga = self.pga_dropdown.currentText()
        pga = 2**int(self.DSTAT_PGA[pga])

        match exp_type:
            case 'Potentiometry':
                V = (raw/(pga/2))*(1.5/8388607.)
            case 'Voltammetry':
                V = (raw-32768)*(3./65636)
            case _:
                self.msg("Error: Unknown UI experiment")

        return V

    # Convert a raw ADC/DAC value from DStat to current
    def correct_current(self, raw):

        # PGA gain is 2^(DStat gain setting)
        pga = self.pga_dropdown.currentText()
        #pga = 2**int(self.DSTAT_PGA[pga])
        pga = int(self.DSTAT_PGA[pga])

        gain = self.gain_dropdown.currentText()

        # Gain in ohms
        gain = int(self.DSTAT_GAIN[gain][1])

        I = (raw/(pga/2))*(1.5/gain/8388607.)

        return I

    # Read dictionaries of settings from json file and populate UI
    def load_UI_options(self):
        # Key: UI string for dropdown. Value: Command for DStat
        with open("dstat_options.json", 'r') as fp:
            options = json.load(fp)

        self.DSTAT_PGA   = options["PGA"]
        self.DSTAT_SRATE = options["SRATE"]
        self.DSTAT_GAIN  = options["GAIN"]
        self.DSTAT_BUFF  = options["BUFF"]
        self.DSTAT_EXP   = options["EXP"]

        # Add options to dropdowns like the Sample Rate, Gain etc.
        self.pga_dropdown.addItems(list(self.DSTAT_PGA.keys()))
        self.srate_dropdown.addItems(list(self.DSTAT_SRATE.keys()))
        self.gain_dropdown.addItems(list(self.DSTAT_GAIN.keys()))
        self.ibuffer_dropdown.addItems(list(self.DSTAT_BUFF.keys()))
        self.exptype_dropdown.addItems(list(self.DSTAT_EXP.keys()))

        # Must be called otherwise all panels are visible due to a
        # limitation of QT Designer.
        self.show_exp_panel()

    # Enable and disable user interface elements depending on state
    def set_UI_visibility(self, state):
        match state:
            case "UNCONNECTED":
                self.execute_btn.setEnabled(False)
                self.stop_btn.setEnabled(False)

                self.refresh_btn.setEnabled(True)
                self.port_dropdown.setEnabled(True)
                self.connect_btn.setEnabled(True)

            case "CONNECTED":
                self.execute_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)

                self.refresh_btn.setEnabled(False)
                self.port_dropdown.setEnabled(False)
                self.connect_btn.setEnabled(False)
                self.frame_exp.setEnabled(True)

            case "EXP_STARTED":
                # TODO Allow gain/pga/srate to be adjusted mid exp?
                self.execute_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)

                self.refresh_btn.setEnabled(False)
                self.port_dropdown.setEnabled(False)
                self.connect_btn.setEnabled(False)
                self.frame_exp.setEnabled(False)

            case _:
                self.msg("Error: Unknown UI visibility requested")

    # Show experiment panel
    def show_exp_panel(self):

        exp = self.exptype_dropdown.currentText()

        # Show only selected experiment input frames
        self.frame_potentiometry.hide()
        self.frame_LSV.hide()

        match exp:
            case "Linear Sweep Voltammetry":
                self.frame_LSV.show()
            case "Potentiometry":
                self.frame_potentiometry.show()
            case _:
                self.msg("Error: Unknown experiment type")

    # Shorter wrapper for sending status message to the UI
    def msg(self, s):
        s = "> " + str(s)
        self.status_box.appendPlainText(s)

    # Configure graph labels etc. based on experiment type
    def configure_plot(self, experiment):
        match experiment:
            case "Linear Sweep Voltammetry":
                self.exp_plot.setTitle("Current Vs Voltage", size="14pt")
                self.exp_plot.setLabel("bottom", "Voltage [V]")
                self.exp_plot.setLabel("left", "Current [A]")
            case "Potentiometry":
                self.exp_plot.setTitle("Voltage Vs Time", size="14pt")
                self.exp_plot.setLabel("bottom", "Time [s]")
                self.exp_plot.setLabel("left", "Voltage [V]")
            case _:
                self.msg("Error: Unknown experiment type")

        self.exp_plot.setMouseEnabled(x=False,y=False)
        self.exp_plot.setLabel("right", "") # Padding
        self.exp_plot.showGrid(x=True, y=True)

    # Update plot with latest data from DStat
    def update_plot(self):
        # Exclude first few data points during settling
        self.exp_line.setData(self.exp_data_x[:-2], self.exp_data_y[:-2])

    # Gracefully close the program on exit
    def closeEvent(self, event):

        # When running, confirm with user they actually want to quit
        if self.experiment_active:
            # Dialog box to make sure user actually wants to exit
            close = QtWidgets.QMessageBox()
            close.setIcon(QtWidgets.QMessageBox.Warning)
            close.setWindowTitle("Warning!")
            close.setText("Experiment running. Are you sure you want to exit?")
            close.setStandardButtons(
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)
            close = close.exec()

            if close == QtWidgets.QMessageBox.Yes:
                event.accept()
            else:
                event.ignore()

        else:
            self.connected = False # Signal thread to stop

            # Wait for threads to stop
            while self.threadpool.activeThreadCount() > 0:
                time.sleep(0.1)

    ################################# SIGNALS ##################################

    # Called automatically when UI events (signals) occur
    def connect_signals(self):
        self.stop_btn.clicked.connect(self.stop_exp)
        self.execute_btn.clicked.connect(self.execute_exp)
        self.exptype_dropdown.activated.connect(self.show_exp_panel)
        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn.clicked.connect(self.connect_port)

    # Send command to DStat to stop experiment
    def stop_exp(self):
        self.set_UI_visibility("CONNECTED")
        self.msg("Stopping DStat...")
        self.ser.reset_output_buffer()
        self.ser.write(b'a') # Abort

        # Leave the plot on the graph but write data to file
        # and clear plot lists to prepare for next test.
        self.plot_timer.stop()
        self.exp_data_x = []
        self.exp_data_y = []

        self.experiment_active = False

    # Send commands to DStat to exectute the current experiment
    def execute_exp(self):

        self.plot_timer.start()

        # See communication_protocal.txt in dstat-firmware repo.
        # https://microfluidics.utoronto.ca/gitlab/dstat/dstat-firmware
        # There is a small bug in the instructions, as DStat firmware
        # actually expects '\r\n' rather than just '\n' termination.

        exp_type = self.exptype_dropdown.currentText()
        pga   = self.pga_dropdown.currentText()
        srate = self.srate_dropdown.currentText()
        gain  = self.gain_dropdown.currentText()
        buff  = self.ibuffer_dropdown.currentText()

        self.ser.reset_output_buffer()

        # Set up ADC
        cmd = "EA" + \
              str(self.DSTAT_PGA[pga])     + ' ' +  \
              str(self.DSTAT_SRATE[srate]) + ' ' + \
              str(self.DSTAT_BUFF[buff])   + ' '
        self.ser.write(b'!' + str(len(cmd)).encode("utf-8") + b'\r\n')
        self.ser.write(cmd.encode("utf-8") + b'\r\n')

        # Set gain
        cmd = "EG" + str(self.DSTAT_GAIN[gain][0]) + ' '
        self.ser.write(b'!' + str(len(cmd)).encode("utf-8") + b'\r\n')
        self.ser.write(cmd.encode("utf-8") + b'\r\n')

        # Experiment specific control
        match exp_type:
            case "Potentiometry":
                self.configure_plot(exp_type)
                self.set_UI_visibility("EXP_STARTED")

                # TODO 1 or 0 here? DStat code says 2 electrode for pot?
                cmd = 'EP' + str(int(self.pot_time.value())) + " 1"
                self.ser.write(b'!' + str(len(cmd)).encode("utf-8") + b'\r\n')
                self.ser.write(cmd.encode("utf-8") + b'\r\n')

            case "Linear Sweep Voltammetry":
                self.configure_plot(exp_type)
                self.set_UI_visibility("EXP_STARTED")

                '''
                    This isn't documented anywhere, but since the dstat
                    accepts 2 byte values as parameters, it rescales some
                    to make better use of this data type. Many of the
                    experiment files like lsv.py do this conversion of
                    integers before sending to the dstat as a command
                '''

                # Preconditioning
                v_precond1 = str(int(self.lsv_vclean.value()*(65536./3000)+32768))
                v_precond2 = str(int(self.lsv_vdep.value()*(65536./3000)+32768))
                t_precond1 = str(int(self.lsv_tclean.value()))
                t_precond2 = str(int(self.lsv_tdep.value()))

                # LSV
                slope = str(int(self.lsv_slope.value()*(65536./3000)))
                start = str(int(self.lsv_start_mV.value()*(65536./3000)+32768))
                stop = str(int(self.lsv_stop_mV.value()*(65536./3000)+32768))

                cmd = 'EL' + t_precond1 + ' ' + t_precond2 + ' ' + \
                      v_precond1 + ' ' + v_precond2 + ' ' + start + \
                      ' ' + stop + ' ' + slope + ' '

                self.ser.write(b'!' + str(len(cmd)).encode("utf-8") + b'\r\n')
                self.ser.write(cmd.encode("utf-8") + b'\r\n')
                        
            case _:
                self.msg("Error: Unknown experiment type")
                return

        self.experiment_active = True

    # Look for potential serial ports and add them to the dropdown 
    def refresh_ports(self):

        ports = []
        try:
            ports, _, _ = zip(*list_ports.grep("DSTAT"))
        except ValueError:
            ports = []
            self.msg("No DStat device found.")

        self.port_dropdown.addItems(ports)

    # Connect to the port selected in port_dropdown
    def connect_port(self):

        ser_port = self.port_dropdown.currentText()

        if ser_port == "":
            self.msg("Error: No port defined to connect to.")
            return

        connected = False
        for i in range(5):
            time.sleep(1) # Give OS time to enumerate
        
            try:
                self.ser = serial.Serial(ser_port, timeout=1)
                self.msg("Connecting...")
                time.sleep(.5)
                connected = True
            except serial.SerialException:
                pass
            
            if connected is True:
                break
        
        try:
            if self.ser.isOpen() is False:
                self.msg("Error: Serial port failed to open")
                self.set_UI_visibility("UNCONNECTED")
                return 1
        except UnboundLocalError:  # ser doesn't exist
            self.msg("Error: Serial port failed to open")
            return 1
            
        # Test connection by querying DStat
        self.ser.write(str.encode('!0\r\n'))
        for i in range(10):
            if self.ser.readline().rstrip()==b"@ACK 0":
                if self.ser.readline().rstrip()==b"@RCV 0":

                    self.msg("Successfully connected to DStat!")
                    self.set_UI_visibility("CONNECTED")
                    self.connected = True

                    # Thread to collect serial data from DStat
                    self.connected = True
                    serial_worker = worker.Worker(self.read_serial)
                    serial_worker.signals.msg.connect(self.msg)
                    self.threadpool.start(serial_worker)
                    break
            else:
                time.sleep(.5)
                self.ser.reset_input_buffer()
                self.ser.write(str.encode('!0 '))
                time.sleep(.1)

if __name__ == "__main__":

    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.exec()
