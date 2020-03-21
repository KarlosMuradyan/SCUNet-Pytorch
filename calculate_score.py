import parmap

import torch
import torchaudio
import numpy as np
import musdb
import mir_eval
from transforms import Normalize


def calculate_score(model, model_weights_path, musdb_dir='musdb', n_workers=1, n_fft=2048,
                    hop_length=512, slice_duration=2):
    mus = musdb.DB(root_dir=musdb_dir)
    music_list = mus.load_mus_tracks(subsets='test')

    model_weights = torch.load(model_weights_path)
    model.load_state_dict(model_weights)
    # model.cuda()
    scores = parmap.map(calculate_SDR, music_list, pm_processes=n_workers, pm_pbar=True,
                        model=model, n_fft=n_fft,
                        hop_length=hop_length, slice_duration=slice_duration)

    print(scores)
    print(np.mean(scores))
    print(np.median(scores))

    torch.save(scores, 'scores')


def calculate_SDR(music, model, n_fft=2048,
                  hop_length=512, slice_duration=2):
    model.eval()
    scores = []
    sr = music.rate
    ind = 0
    mixture = torch.mean(music.audio.transpose(), dim=0)
    vocal = torch.mean(music.targets['vocals'].audio.transpose(), dim=0)
    for i in range(0, len(music.audio), slice_duration * sr):
        ind += 1
        mixture = mixture[i:i + slice_duration * sr]
        vocal = vocal[i:i + slice_duration * sr]
        
        if np.all(vocal == 0):
            # print('[!] -  all 0s, skipping')
            continue
        
        if i + 2 * sr >= len(music.audio):
            break
        resampled_mixture = mixture
        mixture_stft = torch.stft(resampled_mixture, n_fft=n_fft, hop_length=hop_length,
                                           window=torch.hann_window(n_fft), center=True)
        magnitude_mixture_stft, mixture_phase = torchaudio.functional.magphase(mixture_stft)
        normalized_magnitude_mixture_stft = torch.Tensor(Normalize().forward([magnitude_mixture_stft])[0])

        sr_v = music.rate
        with torch.no_grad():
            mask = model.forward(normalized_magnitude_mixture_stft.unsqueeze(0)).squeeze(0)
            out = mask * torch.Tensor(normalized_magnitude_mixture_stft)
        predicted_vocal_stft = out.numpy() * mixture_phase
        predicted_vocal_audio = torch.stft(predicted_vocal_stft.squeeze(0), n_fft=n_fft, hop_length=hop_length,
                                           window=torch.hann_window(n_fft), center=True)
        try:
            scores.append(
                mir_eval.separation.bss_eval_sources(vocal[:predicted_vocal_audio.shape[0]],
                                                     predicted_vocal_audio)[0])
        except ValueError:
            print(vocal.all() == 0)
            print(predicted_vocal_stft.all() == 0)
            print('Error but skipping')
    #         print(score/ind)
