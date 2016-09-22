__author__ = 'drjfunk'

import astropy.io.fits as fits
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import warnings

from OGIPLike import OGIPLike
from threeML.plugin_prototype import PluginPrototype
from OGIP.eventlist import EventList
from threeML.io.rich_display import display

from threeML.io.step_plot import step_plot

__instrument_name = "Fermi GBM TTE (all detectors)"


class FermiGBMLikeTTE(OGIPLike, PluginPrototype):
    def __init__(self, name, tte_file, background_selections, source_intervals, rsp_file, trigger_time=None,
                 poly_order=-1):
        """
        If the input files are TTE files. Background selections are specified as
        a comma separated string e.g. "-10-0,10-20"

        Initial source selection is input as a string e.g. "0-5"

        One can choose a background polynomial order by hand (up to 4th order)
        or leave it as the default polyorder=-1 to decide by LRT test

        FermiGBM_TTE_Like("GBM","glg_tte_n6_bn080916412.fit","-10-0,10-20","0-5","rspfile.rsp{2}")
        to load the second spectrum, second background spectrum and second response.
        """

        self.name = name

        self._gbm_tte_file = GBMTTEFile(tte_file)

        if trigger_time is not None:
            self._gbm_tte_file.set_trigger_time(trigger_time)

        self._evt_list = EventList(arrival_times=self._gbm_tte_file._events - self._gbm_tte_file.triggertime,
                                   energies=self._gbm_tte_file._pha,
                                   n_channels=self._gbm_tte_file._n_channels,
                                   start_time=self._gbm_tte_file._start_events - self._gbm_tte_file.triggertime,
                                   stop_time=self._gbm_tte_file._stop_events - self._gbm_tte_file.triggertime,
                                   dead_time=self._gbm_tte_file._deadtime,
                                   first_channel=0)

        self._evt_list.poly_order = poly_order

        self._backgroundexists = False
        self._energyselectionexists = False

        # Fit the background and
        # Obtain the counts for the initial input interval
        # which is embedded in the background call

        # First get the initial tmin and tmax


        self._startup = True  # This keeps things from being called twice!

        source_intervals = [interval.replace(' ', '') for interval in source_intervals.split(',')]
        background_selections = [interval.replace(' ', '') for interval in background_selections.split(',')]

        self.set_active_time_interval(*source_intervals)
        self.set_background_interval(*background_selections)

        self._startup = False

        self._rsp_file = rsp_file

        OGIPLike.__init__(self, name, pha_file=self._observed_pha, bak_file=self._bkg_pha, rsp_file=rsp_file)

    def __set_poly_order(self, value):
        """Background poly order setter """

        self._evt_list.poly_order = value

    def ___set_poly_order(self, value):
        """ Indirect poly order setter """

        self.__set_poly_order(value)

    def __get_poly_order(self):
        """ Get poly order """
        return self._evt_list.poly_order

    def ___get_poly_order(self):
        """ Indirect poly order getter """

        return self.__get_poly_order()

    background_poly_order = property(___get_poly_order, ___set_poly_order,
                                     doc="Get or set the background polynomial order")

    def set_active_time_interval(self, *intervals):
        '''Set the time interval to be used during the analysis.
        For now, only one interval can be selected. This may be
        updated in the future to allow for self consistent time
        resolved analysis.
        Specified as 'tmin-tmax'. Intervals are in seconds. Example:

        set_active_time_interval("0.0-10.0")

        which will set the energy range 0-10. seconds.
        '''

        self._evt_list.set_active_time_intervals(*intervals)

        self._observed_pha = self._evt_list.get_pha_container(use_poly=False)

        self._active_interval = intervals

        if not self._startup:

            self._bkg_pha = self._evt_list.get_pha_container(use_poly=True)

            OGIPLike.__init__(self, self.name, pha_file=self._observed_pha, bak_file=self._bkg_pha,
                              rsp_file=self._rsp_file)

    def set_background_interval(self, *intervals):
        '''Set the time interval to fit the background.
        Multiple intervals can be input as separate arguments
        Specified as 'tmin-tmax'. Intervals are in seconds. Example:

        setBackgroundInterval("-10.0-0.0","10.-15.")
        '''

        self._evt_list.set_polynomial_fit_interval(*intervals)

        # In theory this will automatically get the poly counts if a
        # time interval already exists

        self._bkg_pha = self._evt_list.get_pha_container(use_poly=True)

        if not self._startup:

            OGIPLike.__init__(self, self.name, pha_file=self._observed_pha, bak_file=self._bkg_pha,
                              rsp_file=self._rsp_file)






    def view_lightcurve(self, start=-10, stop=20., dt=1.):

        binner = np.arange(start, stop + dt, dt)
        cnts, bins = np.histogram(self._gbm_tte_file._events - self._gbm_tte_file.triggertime, bins=binner)
        time_bins = np.array([[bins[i], bins[i + 1]] for i in range(len(bins) - 1)])

        bkg = []
        for tb in time_bins:
            tmpbkg = 0.  # Maybe I can do this perenergy at some point
            for poly in self._evt_list.polynomials:
                tmpbkg += poly.integral(tb[0], tb[1]) / (dt)

            bkg.append(tmpbkg)

        gbm_light_curve_plot(time_bins, cnts, bkg, dt,
                             selection=zip(self._evt_list.tmin_list, self._evt_list._tmax_list))

    def peek(self):

        print "TTE File Info:"

        self._evt_list.peek()

        print 'Timing Info:'

        self._gbm_tte_file.peek()




class GBMTTEFile(object):
    def __init__(self, ttefile):
        '''
        A simple class for opening and easily accessing Fermi GBM
        TTE Files.

        :param ttefile: The filename of the TTE file to be stored

        '''

        tte = fits.open(ttefile)

        self._events = tte['EVENTS'].data['TIME']
        self._pha = tte['EVENTS'].data['PHA']

        try:
            self.triggertime = tte['PRIMARY'].header['TRIGTIME']


        except:

            # For continuous data
            warnings.warn("There is no trigger time in the TTE file. Must me set manually or using MET relative times.")

            self.triggertime = 0

        self._start_events = tte['PRIMARY'].header['TSTART']
        self._stop_events = tte['PRIMARY'].header['TSTOP']

        self._utc_start = tte['PRIMARY'].header['DATE-OBS']
        self._utc_stop = tte['PRIMARY'].header['DATE-END']

        self._n_channels = tte['EBOUNDS'].header['NAXIS2']

        self._calculate_deattime()

    @property
    def start_events(self):
        return self._start_events

    @property
    def stop_events(self):
        return self._stop_events

    @property
    def arrival_times(self):
        return self._events

    @property
    def n_channels(self):
        return self._n_channels

    @property
    def deadtime(self):
        return self._deadtime

    def _calculate_deattime(self):
        """
        Computes an array of deadtimes following the perscription of Meegan et al. (2009).

        The array can be summed over to obtain the total dead time

        """
        self._deadtime = np.zeros_like(self._events)
        overflow_mask = self._pha == self._n_channels  # specific to gbm! should work for CTTE

        # From Meegan et al. (2009)
        # Dead time for overflow (note, overflow sometimes changes)
        self._deadtime[overflow_mask] = 10.E-6  # s

        # Normal dead time
        self._deadtime[~overflow_mask] = 2.E-6  # s

    def peek(self):

        mission_dict = self._compute_mission_times()

        fermi_dict = {}

        fermi_dict['Fermi Trigger Time'] = self.triggertime
        fermi_dict['Fermi MET OBS Start'] = self._start_events
        fermi_dict['Fermi MET OBS Stop'] = self._stop_events
        fermi_dict['Fermi UTC OBS Start'] = self._utc_start
        fermi_dict['Fermi UTC OBS Stop'] = self._utc_stop

        if mission_dict is not None:
            mission_df = pd.Series(mission_dict)

            display(mission_df)

        fermi_df = pd.Series(fermi_dict)

        display(fermi_df)


def gbm_light_curve_plot(time_bins, cnts, bkg, width, selection):
    fig = plt.figure(777)
    ax = fig.add_subplot(111)

    max_cnts = max(cnts / width)
    top = max_cnts + max_cnts * .2
    min_cnts = min(cnts[cnts > 0] / width)
    bottom = min_cnts - min_cnts * .05
    mean_time = map(np.mean, time_bins)

    all_masks = []

    step_plot(time_bins, cnts / width, ax, color='#8da0cb', label="Light Curve")

    for tmin, tmax in selection:
        tmp_mask = np.logical_and(time_bins[:, 0] >= tmin, time_bins[:, 1] <= tmax)

        all_masks.append(tmp_mask)

    if len(all_masks) > 1:

        for mask in all_masks[1:]:
            step_plot(time_bins[mask], cnts[mask] / width, ax,
                      color='#fc8d62',
                      fill=True,
                      fill_min=min_cnts)

    step_plot(time_bins[all_masks[0]], cnts[all_masks[0]] / width, ax,
              color='#fc8d62',
              fill=True,
              fill_min=min_cnts, label="Selection")

    ax.plot(mean_time, bkg, '#66c2a5', lw=2., label="Background")

    # ax.fill_between(selection, bottom, top, color="#fc8d62", alpha=.4)

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Rate (cnts/s)")
    ax.set_ylim(bottom, top)
    ax.legend()
